import pandas as pd
import pytest

from zhongwen_anki.enrich import OUTPUT_COLUMNS, REQUIRED_COLS, generate_flashcards, output_columns


def _write_tsv(path, rows, columns):
    pd.DataFrame(rows, columns=columns).to_csv(path, sep="\t", index=False)


def test_generate_flashcards_basic(tmp_path):
    input_path = tmp_path / "input.tsv"
    output_path = tmp_path / "output.tsv"
    columns = REQUIRED_COLS + ["MeaningES", "SentenceMeaningES", "SynonymsES", "DictionaryMeaningES"]
    rows = [[
        "你好", "你好", "nǐ hǎo", "hello", "你好。", "Hello.", "",
        "问候语", "greeting", "hola", "Hola.", "", "saludo",
    ]]
    _write_tsv(input_path, rows, columns)

    generate_flashcards(input_path, output_path)

    out = pd.read_csv(output_path, sep="\t", dtype=str).fillna("")
    assert list(out.columns) == OUTPUT_COLUMNS
    assert len(out) == 1
    row = out.iloc[0]
    assert row["Simplified"] == "你好"
    assert row["Hint"] == "你"
    assert row["MeaningES"] == "hola"
    assert 'tone-' in row["SimplifiedColored"]
    assert row["SentencePinyin"]  # auto-generated from the sentence, non-empty


def test_generate_flashcards_missing_required_column(tmp_path):
    input_path = tmp_path / "input.tsv"
    output_path = tmp_path / "output.tsv"
    columns = [c for c in REQUIRED_COLS if c != "Meaning"]
    rows = [["你好", "你好", "nǐ hǎo", "你好。", "Hello.", "", "问候语", "greeting"]]
    _write_tsv(input_path, rows, columns)

    with pytest.raises(SystemExit):
        generate_flashcards(input_path, output_path)


def test_generate_flashcards_optional_columns_default_to_empty(tmp_path):
    input_path = tmp_path / "input.tsv"
    output_path = tmp_path / "output.tsv"
    rows = [["你好", "你好", "nǐ hǎo", "hello", "你好。", "Hello.", "", "问候语", "greeting"]]
    _write_tsv(input_path, rows, REQUIRED_COLS)

    generate_flashcards(input_path, output_path)

    out = pd.read_csv(output_path, sep="\t", dtype=str).fillna("")
    assert out.iloc[0]["MeaningES"] == ""
    assert out.iloc[0]["SynonymsES"] == ""


def test_generate_flashcards_drops_duplicate_simplified(tmp_path):
    input_path = tmp_path / "input.tsv"
    output_path = tmp_path / "output.tsv"
    row = ["你好", "你好", "nǐ hǎo", "hello", "你好。", "Hello.", "", "问候语", "greeting"]
    _write_tsv(input_path, [row, row], REQUIRED_COLS)

    generate_flashcards(input_path, output_path)

    out = pd.read_csv(output_path, sep="\t", dtype=str)
    assert len(out) == 1


def test_generate_flashcards_supports_a_custom_target_lang(tmp_path):
    """--target-lang generalizes the pipeline beyond Spanish: any suffix
    reads/writes its own set of translation columns (e.g. "FR" ->
    MeaningFR, SentenceMeaningFR, SynonymsFR, DictionaryMeaningFR)."""
    input_path = tmp_path / "input.tsv"
    output_path = tmp_path / "output.tsv"
    columns = REQUIRED_COLS + ["MeaningFR", "SentenceMeaningFR", "SynonymsFR", "DictionaryMeaningFR"]
    rows = [[
        "你好", "你好", "nǐ hǎo", "hello", "你好。", "Hello.", "",
        "问候语", "greeting", "bonjour", "Bonjour.", "", "salutation",
    ]]
    _write_tsv(input_path, rows, columns)

    generate_flashcards(input_path, output_path, target_lang="FR")

    out = pd.read_csv(output_path, sep="\t", dtype=str).fillna("")
    assert list(out.columns) == output_columns("FR")
    assert out.iloc[0]["MeaningFR"] == "bonjour"
    assert "MeaningES" not in out.columns
