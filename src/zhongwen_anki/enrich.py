import argparse
from pathlib import Path
from typing import List

import pandas as pd

from zhongwen_anki.utilities import (
    sentence_to_words,
    words_to_hanzi,
    words_to_pinyin,
    words_to_colored_hanzi,
    process_synonyms,
)

DEFAULT_TARGET_LANG = "ES"

# Base field names that get a language-suffixed twin (e.g. "Meaning" + "ES"
# -> "MeaningES") holding a translation into --target-lang, kept alongside
# the English value rather than replacing it, so they can be checked against
# one another. Pass --target-lang to prepare a deck for a native language
# other than Spanish: the input TSV then needs e.g. "MeaningFR" instead of
# "MeaningES", and the card templates in card_template/ must be updated to
# reference the matching {{FieldFR}} placeholders (see build_deck.py).
TRANSLATABLE_FIELDS: List[str] = ["Meaning", "SentenceMeaning", "Synonyms", "DictionaryMeaning"]

REQUIRED_COLS: List[str] = [
    "Simplified", "Traditional", "Pinyin", "Meaning",
    "SentenceSimplified", "SentenceMeaning", "Synonyms",
    "DictionarySimplified", "DictionaryMeaning",
]


def _lang_col(field: str, target_lang: str) -> str:
    return f"{field}{target_lang}"


def optional_cols(target_lang: str = DEFAULT_TARGET_LANG) -> List[str]:
    """Translation columns for *target_lang*. Absent from the input TSV,
    they default to empty rather than being required."""
    return [_lang_col(field, target_lang) for field in TRANSLATABLE_FIELDS]


def output_columns(target_lang: str = DEFAULT_TARGET_LANG) -> List[str]:
    return [
        "Simplified", "SimplifiedColored",
        "Traditional", "TraditionalColored",
        "Pinyin", "Meaning", _lang_col("Meaning", target_lang), "Hint",
        "SentenceSimplified", "SentenceSimplifiedColored", "SentenceMeaning",
        _lang_col("SentenceMeaning", target_lang), "SentencePinyin",
        "Synonyms", "SynonymsColored", _lang_col("Synonyms", target_lang),
        "DictionarySimplified", "DictionarySimplifiedColored", "DictionaryPinyin",
        "DictionaryMeaning", _lang_col("DictionaryMeaning", target_lang),
    ]


# Backwards-compatible aliases for the default (Spanish) deck.
OPTIONAL_COLS: List[str] = optional_cols()
OUTPUT_COLUMNS: List[str] = output_columns()


def _transform_row(row: pd.Series, target_lang: str = DEFAULT_TARGET_LANG) -> dict:
    """Return a fully processed row ready for output."""
    simplified_words = sentence_to_words(row["Simplified"])
    traditional_words = sentence_to_words(row["Traditional"])
    sentence_words = sentence_to_words(row["SentenceSimplified"])
    dictionary_words = sentence_to_words(row["DictionarySimplified"].replace(" ", ""))

    return {
        # Primary fields
        "Simplified": row["Simplified"],
        "SimplifiedColored": words_to_colored_hanzi(simplified_words),
        "Traditional": row["Traditional"],
        "TraditionalColored": words_to_colored_hanzi(traditional_words),
        "Pinyin": row["Pinyin"],
        "Meaning": row["Meaning"],
        _lang_col("Meaning", target_lang): row[_lang_col("Meaning", target_lang)],
        "Hint": row["Simplified"][0],
        # Sentence
        "SentenceSimplified": words_to_hanzi(sentence_words),
        "SentenceSimplifiedColored": words_to_colored_hanzi(sentence_words, sep=""),
        "SentenceMeaning": row["SentenceMeaning"],
        _lang_col("SentenceMeaning", target_lang): row[_lang_col("SentenceMeaning", target_lang)],
        "SentencePinyin": words_to_pinyin(sentence_words),
        # Synonyms
        "Synonyms": row["Synonyms"],
        "SynonymsColored": process_synonyms(row["Synonyms"]),
        _lang_col("Synonyms", target_lang): row[_lang_col("Synonyms", target_lang)],
        # Dictionary
        "DictionarySimplified": words_to_hanzi(dictionary_words),
        "DictionarySimplifiedColored": words_to_colored_hanzi(dictionary_words, sep=""),
        "DictionaryPinyin": words_to_pinyin(dictionary_words),
        "DictionaryMeaning": row["DictionaryMeaning"],
        _lang_col("DictionaryMeaning", target_lang): row[_lang_col("DictionaryMeaning", target_lang)],
    }


def generate_flashcards(
    input_path: Path, output_path: Path, target_lang: str = DEFAULT_TARGET_LANG
) -> None:
    """Read *input_path* TSV, enrich it, and write to *output_path*.

    The TSV **must** contain at least the columns listed in `REQUIRED_COLS`.
    Extra columns are silently ignored. Translation columns are named after
    *target_lang* (e.g. "MeaningES" for target_lang="ES", the default).
    """
    df = pd.read_csv(input_path, sep="\t", dtype=str)

    missing_required = [col for col in REQUIRED_COLS if col not in df.columns]
    if missing_required:
        raise SystemExit(
            f"Input file {input_path} is missing one or more required "
            f"columns: {', '.join(missing_required)}"
        )

    # fill NaN with empty string to avoid None issues downstream
    df = df.fillna("")

    # optional columns (e.g. translations) default to empty if absent
    for col in optional_cols(target_lang):
        if col not in df.columns:
            df[col] = ""

    before = len(df)
    df = df.drop_duplicates(subset="Simplified", keep="first")
    after = len(df)
    if after < before:
        print(f"Removed {before - after:,} duplicate rows based on 'Simplified'.")

    columns = output_columns(target_lang)
    processed_rows = [_transform_row(row, target_lang) for _, row in df.iterrows()]
    out_df = pd.DataFrame(processed_rows, columns=columns)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output_path, sep="\t", index=False, encoding="utf-8")

    print(f"Wrote {len(out_df):,} cards -> {output_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="zhongwen-anki",
        description="Generate Chinese flashcards with tone colouring.",
    )
    parser.add_argument("-i", "--input", type=Path, required=True, metavar="INPUT.tsv",
                        help="Path to a word list, e.g. data/hsk1/input.tsv (TSV).")
    parser.add_argument("-o", "--output", type=Path, required=True, metavar="OUTPUT.tsv",
                        help="Destination TSV for Anki.")
    parser.add_argument(
        "--target-lang", type=str, default=DEFAULT_TARGET_LANG, metavar="LANG",
        help=(
            "Suffix identifying the translation columns to read (e.g. 'ES' reads "
            "MeaningES/SentenceMeaningES/SynonymsES/DictionaryMeaningES). Change this "
            "to adapt the deck to a native language other than Spanish -- the input "
            "TSV needs matching columns and the card templates in card_template/ must "
            f"reference the matching {{{{FieldLANG}}}} placeholders. Default: {DEFAULT_TARGET_LANG}."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    generate_flashcards(args.input, args.output, args.target_lang)


if __name__ == "__main__":
    main()
