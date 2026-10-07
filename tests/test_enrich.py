import pandas as pd
import pytest

from zhongwen_anki.enrich import GUID_COL, OUTPUT_COLUMNS, REQUIRED_COLS, generate_flashcards, output_columns


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
    assert list(out.columns) == OUTPUT_COLUMNS + [GUID_COL]
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


def test_generate_flashcards_keeps_polyphonic_readings(tmp_path):
    """Same character, different Pinyin (e.g. 还 hái "still" vs huán "to
    return") are distinct vocabulary entries and must both survive, not just
    the first one -- only an exact (Simplified, Pinyin) match is a dup."""
    input_path = tmp_path / "input.tsv"
    output_path = tmp_path / "output.tsv"
    row_a = ["还", "還", "hái", "still, also", "他还没到。", "He hasn't arrived yet.", "", "仍旧", "still"]
    row_b = ["还", "還", "huán", "to return", "请把书还给我。", "Please return the book to me.", "", "归还", "to return"]
    _write_tsv(input_path, [row_a, row_b], REQUIRED_COLS)

    generate_flashcards(input_path, output_path)

    out = pd.read_csv(output_path, sep="\t", dtype=str)
    assert len(out) == 2
    assert set(out["Pinyin"]) == {"hái", "huán"}


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
    assert list(out.columns) == output_columns("FR") + [GUID_COL]
    assert out.iloc[0]["MeaningFR"] == "bonjour"
    assert "MeaningES" not in out.columns


def test_generate_flashcards_keeps_different_senses_with_the_same_reading(tmp_path):
    """生 shēng "to give birth" and 生 shēng "raw" are two vocabulary
    entries: only an exact (Simplified, Pinyin, Meaning) match is a dup."""
    input_path = tmp_path / "input.tsv"
    output_path = tmp_path / "output.tsv"
    row_a = ["生", "生", "shēng", "to give birth", "她生了一个女儿。", "She gave birth to a daughter.", "", "出生", "to be born"]
    row_b = ["生", "生", "shēng", "raw, uncooked", "这块肉还是生的。", "This meat is still raw.", "", "没有煮熟", "not cooked"]
    _write_tsv(input_path, [row_a, row_b], REQUIRED_COLS)

    generate_flashcards(input_path, output_path)

    out = pd.read_csv(output_path, sep="	", dtype=str)
    assert list(out["Meaning"]) == ["to give birth", "raw, uncooked"]


def test_generate_flashcards_passes_the_frozen_guid_through(tmp_path):
    input_path = tmp_path / "input.tsv"
    output_path = tmp_path / "output.tsv"
    row = ["你好", "你好", "nǐ hǎo", "hello", "你好。", "Hello.", "", "问候语", "greeting", "abc123"]
    _write_tsv(input_path, [row], REQUIRED_COLS + [GUID_COL])

    generate_flashcards(input_path, output_path)

    out = pd.read_csv(output_path, sep="	", dtype=str)
    assert out.iloc[0][GUID_COL] == "abc123"


def test_synonyms_colored_uses_the_target_language(tmp_path):
    """The colored synonyms replace the plain target-language ones on the
    cards, so they must carry the same (target-language) translations."""
    input_path = tmp_path / "input.tsv"
    output_path = tmp_path / "output.tsv"
    columns = REQUIRED_COLS + ["SynonymsES"]
    row = ["全部", "全部", "quánbù", "all", "全部来了。", "All came.",
           "全部 (quán bù) - all, everything", "所有", "all",
           "全部 (quán bù) - todo, la totalidad"]
    _write_tsv(input_path, [row], columns)

    generate_flashcards(input_path, output_path)

    colored = pd.read_csv(output_path, sep="\t", dtype=str).iloc[0]["SynonymsColored"]
    assert "todo, la totalidad" in colored
    assert "everything" not in colored
    assert "tone-" in colored
