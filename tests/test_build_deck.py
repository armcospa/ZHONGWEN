import pandas as pd
import pytest

from zhongwen_anki.build_deck import DECK_IDS, build_deck, build_model
from zhongwen_anki.enrich import OUTPUT_COLUMNS

EXPECTED_TEMPLATE_NAMES = [
    "Hanzi -> Significado",
    "Significado -> Hanzi",
    "Escribir Pinyin",
    "Escribir Hanzi",
    "Pinyin -> Significado",
]


def test_build_model_has_one_field_per_output_column():
    model = build_model(OUTPUT_COLUMNS)
    assert [f["name"] for f in model.fields] == OUTPUT_COLUMNS


def test_build_model_has_the_five_expected_templates():
    model = build_model(OUTPUT_COLUMNS)
    assert [t["name"] for t in model.templates] == EXPECTED_TEMPLATE_NAMES
    for template in model.templates:
        assert template["qfmt"].strip()
        assert template["afmt"].strip()


def test_build_model_target_lang_relabels_the_translation_fields():
    """A non-default --target-lang must rewrite the {{FieldES}} placeholders
    baked into the static card templates to {{FieldXX}} so they line up with
    the note's actual (renamed) fields."""
    model = build_model(OUTPUT_COLUMNS, target_lang="FR")
    back = model.templates[0]["afmt"]  # "Hanzi -> Significado"
    assert "{{MeaningES}}" not in back
    assert "{{MeaningFR}}" in back
    assert "{{SynonymsFR}}" in back
    assert "{{DictionaryMeaningFR}}" in back


def _write_minimal_output_tsv(tmp_path):
    row = {col: "" for col in OUTPUT_COLUMNS}
    row["Simplified"] = "你好"
    row["Pinyin"] = "nǐ hǎo"
    row["Meaning"] = "hello"
    input_tsv = tmp_path / "output.tsv"
    pd.DataFrame([row]).to_csv(input_tsv, sep="\t", index=False)
    return input_tsv


def test_build_deck_writes_a_nonempty_apkg(tmp_path):
    input_tsv = _write_minimal_output_tsv(tmp_path)
    output_apkg = tmp_path / "deck.apkg"
    build_deck(input_tsv, output_apkg)

    assert output_apkg.exists()
    # A real deck.apkg (library + embedded stroke data + a note) is at least
    # a few hundred KB; a near-empty file would mean something got dropped.
    assert output_apkg.stat().st_size > 100_000


def test_build_deck_supports_every_known_hsk_level(tmp_path):
    input_tsv = _write_minimal_output_tsv(tmp_path)
    for level in DECK_IDS:
        output_apkg = tmp_path / f"{level}.apkg"
        build_deck(input_tsv, output_apkg, level=level)
        assert output_apkg.exists()


def test_build_deck_rejects_an_unregistered_level(tmp_path):
    input_tsv = _write_minimal_output_tsv(tmp_path)
    with pytest.raises(SystemExit):
        build_deck(input_tsv, tmp_path / "deck.apkg", level="HSK9")
