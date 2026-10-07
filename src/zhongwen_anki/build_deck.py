"""Build a deck.apkg from an output TSV using the HTML/CSS in card_template/.

Usage:
    python -m zhongwen_anki.build_deck -i data/hsk1/output.tsv -o decks/HSK1.apkg --level HSK1
"""
import argparse
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, Optional

import genanki
import pandas as pd

from zhongwen_anki import hanzi_writer
from zhongwen_anki.enrich import DEFAULT_TARGET_LANG, GUID_COL, TRANSLATABLE_FIELDS, output_columns

MODEL_ID = 1607392319

# Stable genanki IDs, one per HSK level. genanki/Anki match decks by ID, not
# by name: never change an existing level's ID once a deck has been shared,
# or the next import will create a duplicate deck instead of updating the
# existing one. Add a new stable ID here to support a further level.
DECK_IDS = {
    "HSK1": 2059400110,
    "HSK2": 2059400111,
    "HSK3": 2059400112,
    "HSK4": 2059400113,
}

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "card_template"
SHARED_DIR = TEMPLATE_DIR / "_shared"

# (template name, folder under card_template/). Order matters: cards.ord is
# this list's index, used to label reviews by card type in
# export_stats.CARD_TYPE_BY_ORD without depending on genanki. Only ever
# APPEND new templates here -- never reorder or insert in the middle, or
# existing cards' `ord` (and their whole review history/scheduling) would
# silently point at the wrong template next time this deck is rebuilt and
# reimported.
TEMPLATES = [
    ("H2M", "h2m"),
    ("M2H", "m2h"),
    ("H2P", "h2p"),
    ("PM2H", "pm2h"),
    ("P2M", "p2m"),
    ("M2P", "m2p"),
    ("P2H", "p2h"),
    ("HM2P", "hm2p"),
    ("HP2M", "hp2m"),
    ("Toda la información", "all_information"),
]

# `<!-- include: name -->` pulls in card_template/_shared/name.html, so the
# blocks every card repeats (details, the "Unhide" button, the level badge,
# the hanzi quiz...) live in one place. `hanzi_writer` is special: it is
# generated in memory (see zhongwen_anki.hanzi_writer).
_INCLUDE_RE = re.compile(r"<!-- include: (\w+) -->")
HANZI_WRITER_INCLUDE = "hanzi_writer"


def _resolve_includes(html: str, hanzi_bundle: str, seen: tuple = ()) -> str:
    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name == HANZI_WRITER_INCLUDE:
            return hanzi_bundle
        if name in seen:
            raise ValueError(f"Circular include: {' -> '.join(seen + (name,))}")
        path = SHARED_DIR / f"{name}.html"
        if not path.exists():
            raise FileNotFoundError(f"Unknown include '{name}': {path} does not exist")
        partial = path.read_text(encoding="utf-8").rstrip("\n")
        return _resolve_includes(partial, hanzi_bundle, seen + (name,))

    return _INCLUDE_RE.sub(replace, html)


def _read(path: Path, target_lang: str = DEFAULT_TARGET_LANG, hanzi_bundle: str = "") -> str:
    html = _resolve_includes(path.read_text(encoding="utf-8"), hanzi_bundle)
    if target_lang != DEFAULT_TARGET_LANG:
        for field in TRANSLATABLE_FIELDS:
            html = html.replace(
                "{{" + field + DEFAULT_TARGET_LANG + "}}",
                "{{" + field + target_lang + "}}",
            )
    return html


def build_model(
    fields: list,
    target_lang: str = DEFAULT_TARGET_LANG,
    hanzi_chars: Optional[Iterable[str]] = None,
) -> genanki.Model:
    """Build the (single, shared-across-levels) note type.

    *fields* should be the column names of the output TSV, in order -- pass
    e.g. `zhongwen_anki.enrich.output_columns(target_lang)`.

    *hanzi_chars* are the characters whose stroke data the hanzi-writing
    cards embed. Default: every character in every data/<level>/input.tsv,
    so every level's deck ships the same note type.
    """
    if hanzi_chars is None:
        hanzi_chars = hanzi_writer.used_characters(hanzi_writer.discover_input_tsvs())
    hanzi_bundle = hanzi_writer.bundle_html(hanzi_chars)

    css = (TEMPLATE_DIR / "styling.css").read_text(encoding="utf-8")
    name = "Chino - HSK (ES/EN)" if target_lang == DEFAULT_TARGET_LANG else f"Chino - HSK ({target_lang}/EN)"
    return genanki.Model(
        MODEL_ID,
        name,
        fields=[{"name": name} for name in fields],
        templates=[
            {
                "name": template_name,
                "qfmt": _read(TEMPLATE_DIR / folder / "front.html", target_lang, hanzi_bundle),
                "afmt": _read(TEMPLATE_DIR / folder / "back.html", target_lang, hanzi_bundle),
            }
            for template_name, folder in TEMPLATES
        ],
        css=css,
    )


def note_guid(simplified: str, pinyin: str, meaning: str, frozen: str = "") -> str:
    """The note's stable GUID: *frozen* (the input TSV's Guid column) when
    present, else one derived only from the word's identity.

    Anki matches reimported notes by GUID. genanki's default derives it from
    *every* field, so any edit (fixing a typo, adding a column) would turn
    the note into a brand-new one on reimport and orphan its review history.
    """
    return frozen or genanki.guid_for(simplified, pinyin, meaning)


def _write_compressed(package: genanki.Package, output_path: Path) -> None:
    """genanki writes .apkg files uncompressed (ZIP_STORED); the inlined
    stroke data compresses very well, so re-zip with DEFLATE."""
    with tempfile.TemporaryDirectory() as tmp:
        raw_path = Path(tmp) / "raw.apkg"
        package.write_to_file(str(raw_path))
        with zipfile.ZipFile(raw_path) as src, \
                zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as dst:
            for item in src.infolist():
                dst.writestr(item.filename, src.read(item.filename))


def build_deck(
    input_path: Path,
    output_path: Path,
    level: str = "HSK1",
    target_lang: str = DEFAULT_TARGET_LANG,
) -> None:
    """Build a deck.apkg for a single HSK *level* from an enriched TSV.

    No media files are needed: the HanziWriter library and the stroke data
    for every character are inlined directly into the hanzi-writing card
    templates (see zhongwen_anki/hanzi_writer.py), because Anki's webview
    has a known race condition where external script/media files aren't
    always loaded in time when a card's inline script runs, especially on
    AnkiDroid.
    """
    if level not in DECK_IDS:
        raise SystemExit(
            f"Unknown level '{level}'. Add a stable deck ID for it to DECK_IDS in "
            f"{Path(__file__).name} first (known levels: {', '.join(DECK_IDS)})."
        )

    df = pd.read_csv(input_path, sep="\t", dtype=str).fillna("")
    fields = output_columns(target_lang)
    if df.columns.tolist() != fields + [GUID_COL]:
        raise SystemExit(
            f"{input_path} does not have the columns this version of zhongwen-anki writes.\n"
            f"Regenerate it with `zhongwen-anki -i <input.tsv> -o {input_path}` first.\n"
            f"Expected: {', '.join(fields + [GUID_COL])}\n"
            f"Found:    {', '.join(df.columns)}"
        )

    # Level the word was introduced in, shown in the corner of every answer.
    df.loc[df["SourceLevel"] == "", "SourceLevel"] = level

    hanzi_chars = hanzi_writer.used_characters(hanzi_writer.discover_input_tsvs())
    for word in df["Simplified"]:
        hanzi_chars.update(word)
    model = build_model(fields, target_lang, hanzi_chars)
    deck = genanki.Deck(DECK_IDS[level], f"Chino - {level} (HSK 3.0)")

    for _, row in df.iterrows():
        note = genanki.Note(
            model=model,
            fields=[row[col] for col in fields],
            tags=[level],
            guid=note_guid(row["Simplified"], row["Pinyin"], row["Meaning"], row[GUID_COL]),
        )
        deck.add_note(note)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_compressed(genanki.Package(deck), output_path)
    print(f"Wrote {len(df):,} notes -> {output_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a deck.apkg from an output TSV.")
    parser.add_argument("-i", "--input", type=Path, required=True, metavar="OUTPUT.tsv")
    parser.add_argument("-o", "--output", type=Path, required=True, metavar="DECK.apkg")
    parser.add_argument(
        "--level", type=str, default="HSK1", metavar="LEVEL",
        help=f"HSK level tag/deck for these notes. Known levels: {', '.join(DECK_IDS)}. Default: HSK1.",
    )
    parser.add_argument(
        "--target-lang", type=str, default=DEFAULT_TARGET_LANG, metavar="LANG",
        help="Must match the --target-lang used with `zhongwen-anki` to generate the input TSV. Default: ES.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    build_deck(args.input, args.output, args.level, args.target_lang)


if __name__ == "__main__":
    main()
