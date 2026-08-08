"""Build a deck.apkg from an output TSV using the HTML/CSS in card_template/.

Usage:
    python -m zhongwen_anki.build_deck -i data/hsk1/output.tsv -o decks/HSK1.apkg --level HSK1
"""
import argparse
from pathlib import Path

import genanki
import pandas as pd

from zhongwen_anki.enrich import DEFAULT_TARGET_LANG, TRANSLATABLE_FIELDS

MODEL_ID = 1607392319

# Stable genanki IDs, one per HSK level. genanki/Anki match decks by ID, not
# by name: never change an existing level's ID once a deck has been shared,
# or the next import will create a duplicate deck instead of updating the
# existing one. Add a new stable ID here to support a further level.
DECK_IDS = {
    "HSK1": 2059400110,
    "HSK2": 2059400111,
    "HSK3": 2059400112,
}

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "card_template"


def _read(path: Path, target_lang: str = DEFAULT_TARGET_LANG) -> str:
    html = path.read_text(encoding="utf-8")
    if target_lang != DEFAULT_TARGET_LANG:
        for field in TRANSLATABLE_FIELDS:
            html = html.replace(
                "{{" + field + DEFAULT_TARGET_LANG + "}}",
                "{{" + field + target_lang + "}}",
            )
    return html


def build_model(fields: list, target_lang: str = DEFAULT_TARGET_LANG) -> genanki.Model:
    """Build the (single, shared-across-levels) note type.

    *fields* should be the column names of the output TSV, in order -- pass
    e.g. `zhongwen_anki.enrich.output_columns(target_lang)`, or read them
    straight off the TSV you're about to build (see `build_deck` below).
    """
    css = (TEMPLATE_DIR / "styling.css").read_text(encoding="utf-8")
    name = "Chino - HSK (ES/EN)" if target_lang == DEFAULT_TARGET_LANG else f"Chino - HSK ({target_lang}/EN)"
    return genanki.Model(
        MODEL_ID,
        name,
        fields=[{"name": name} for name in fields],
        # Order matters: cards.ord (0-4) is this list's index, used to label
        # reviews by card type in export_stats.CARD_TYPE_BY_ORD without
        # depending on genanki. Only ever APPEND new templates here -- never
        # reorder or insert in the middle, or existing cards' `ord` (and
        # their whole review history/scheduling) would silently point at the
        # wrong template next time this deck is rebuilt and reimported.
        templates=[
            {
                "name": "Hanzi -> Significado",
                "qfmt": _read(TEMPLATE_DIR / "chinese_to_english" / "front.html", target_lang),
                "afmt": _read(TEMPLATE_DIR / "chinese_to_english" / "back.html", target_lang),
            },
            {
                "name": "Significado -> Hanzi",
                "qfmt": _read(TEMPLATE_DIR / "english_to_chinese" / "front.html", target_lang),
                "afmt": _read(TEMPLATE_DIR / "english_to_chinese" / "back.html", target_lang),
            },
            {
                "name": "Escribir Pinyin",
                "qfmt": _read(TEMPLATE_DIR / "pinyin_writing" / "front.html", target_lang),
                "afmt": _read(TEMPLATE_DIR / "pinyin_writing" / "back.html", target_lang),
            },
            {
                "name": "Escribir Hanzi",
                "qfmt": _read(TEMPLATE_DIR / "hanzi_writing" / "front.html", target_lang),
                "afmt": _read(TEMPLATE_DIR / "hanzi_writing" / "back.html", target_lang),
            },
            {
                "name": "Pinyin -> Significado",
                "qfmt": _read(TEMPLATE_DIR / "pinyin_to_meaning" / "front.html", target_lang),
                "afmt": _read(TEMPLATE_DIR / "pinyin_to_meaning" / "back.html", target_lang),
            },
        ],
        css=css,
    )


def build_deck(
    input_path: Path,
    output_path: Path,
    level: str = "HSK1",
    target_lang: str = DEFAULT_TARGET_LANG,
) -> None:
    """Build a deck.apkg for a single HSK *level* from an enriched TSV.

    No media files are needed: the HanziWriter library and the stroke data
    for every character are inlined directly into
    card_template/hanzi_writing/front.html and back.html (see
    zhongwen_anki/build_hanzi_templates.py), because Anki's webview has a
    known race condition where external script/media files aren't always
    loaded in time when a card's inline script runs, especially on
    AnkiDroid.
    """
    if level not in DECK_IDS:
        raise SystemExit(
            f"Unknown level '{level}'. Add a stable deck ID for it to DECK_IDS in "
            f"{Path(__file__).name} first (known levels: {', '.join(DECK_IDS)})."
        )

    df = pd.read_csv(input_path, sep="\t", dtype=str).fillna("")
    fields = df.columns.tolist()
    model = build_model(fields, target_lang)
    deck = genanki.Deck(DECK_IDS[level], f"Chino - {level} (HSK 3.0)")

    for _, row in df.iterrows():
        note = genanki.Note(
            model=model,
            fields=[row[col] for col in fields],
            tags=[level],
        )
        deck.add_note(note)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(deck).write_to_file(str(output_path))
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
