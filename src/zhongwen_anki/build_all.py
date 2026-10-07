"""Regenerate every level's output.tsv and deck in one go.

For each data/<level>/input.tsv (e.g. data/hsk2/input.tsv) this runs the
enrich step into data/<level>/output.tsv and packages decks/<LEVEL>.apkg.
Rebuilding all levels together keeps them on the same note type: the note
type (fields, templates, CSS, stroke data) is shared across levels, so a
deck built from older templates would overwrite the newer ones on import.

Usage:
    python -m zhongwen_anki.build_all
    python -m zhongwen_anki.build_all --levels HSK2 HSK3
"""
import argparse
from pathlib import Path
from typing import List, Optional

from zhongwen_anki.build_deck import DECK_IDS, build_deck
from zhongwen_anki.enrich import DEFAULT_TARGET_LANG, generate_flashcards
from zhongwen_anki.hanzi_writer import DATA_DIR, ROOT_DIR, discover_input_tsvs

DECKS_DIR = ROOT_DIR / "decks"


def build_all(
    levels: Optional[List[str]] = None,
    target_lang: str = DEFAULT_TARGET_LANG,
    data_dir: Path = DATA_DIR,
    decks_dir: Path = DECKS_DIR,
) -> List[Path]:
    """Build the decks for *levels* (default: every level with an input.tsv
    under *data_dir*) and return the written .apkg paths."""
    available = {tsv.parent.name.upper(): tsv for tsv in discover_input_tsvs(data_dir)}
    if not available:
        raise SystemExit(f"No input.tsv files found under {data_dir}/*/input.tsv")
    levels = [level.upper() for level in levels] if levels else sorted(available)

    unknown = [level for level in levels if level not in available]
    if unknown:
        raise SystemExit(f"No data/<level>/input.tsv for: {', '.join(unknown)} (found: {', '.join(available)})")
    no_deck_id = [level for level in levels if level not in DECK_IDS]
    if no_deck_id:
        raise SystemExit(f"Add a stable deck ID to DECK_IDS in build_deck.py first for: {', '.join(no_deck_id)}")

    written = []
    for level in levels:
        input_tsv = available[level]
        output_tsv = input_tsv.with_name("output.tsv")
        deck_path = decks_dir / f"{level}.apkg"
        print(f"== {level}")
        generate_flashcards(input_tsv, output_tsv, target_lang)
        build_deck(output_tsv, deck_path, level, target_lang)
        written.append(deck_path)
    return written


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Regenerate every level's output.tsv and deck.")
    parser.add_argument(
        "--levels", nargs="*", default=None, metavar="LEVEL",
        help="Levels to build, e.g. HSK1 HSK3. Default: every data/<level>/input.tsv.",
    )
    parser.add_argument(
        "--target-lang", type=str, default=DEFAULT_TARGET_LANG, metavar="LANG",
        help=f"Translation column suffix, as in `zhongwen-anki --target-lang`. Default: {DEFAULT_TARGET_LANG}.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    build_all(args.levels, args.target_lang)


if __name__ == "__main__":
    main()
