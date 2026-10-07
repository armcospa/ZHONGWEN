import itertools
import json
import sqlite3
import zipfile

import genanki
import pandas as pd
import pytest

from zhongwen_anki.build_deck import DECK_IDS, build_deck, build_model, note_guid
from zhongwen_anki.enrich import GUID_COL, OUTPUT_COLUMNS

EXPECTED_TEMPLATE_NAMES = [
    "H2M",
    "M2H",
    "H2P",
    "PM2H",
    "P2M",
    "M2P",
    "P2H",
    "HM2P",
    "HP2M",
    "Toda la información",
]

# Classes the "Unhide" button reveals; hidden (or not displayed) by default.
TOGGLED_CLASSES = ["PinyinHidden", "sentenceColored", "synonymsColored", "dictionaryColored"]


@pytest.fixture(scope="module")
def model():
    return build_model(OUTPUT_COLUMNS)


def _templates(model):
    return {t["name"]: t for t in model.templates}


def test_build_model_has_one_field_per_output_column(model):
    assert [f["name"] for f in model.fields] == OUTPUT_COLUMNS


def test_build_model_has_the_ten_expected_templates(model):
    assert [t["name"] for t in model.templates] == EXPECTED_TEMPLATE_NAMES
    for template in model.templates:
        assert template["qfmt"].strip()
        assert template["afmt"].strip()


def test_build_model_resolves_every_include(model):
    for template in model.templates:
        for side in ("qfmt", "afmt"):
            assert "<!-- include:" not in template[side], (template["name"], side)


def test_build_model_target_lang_relabels_the_translation_fields():
    """A non-default --target-lang must rewrite the {{FieldES}} placeholders
    baked into the card templates (and their shared includes) to {{FieldXX}}
    so they line up with the note's actual (renamed) fields."""
    model = build_model(OUTPUT_COLUMNS, target_lang="FR")
    back = model.templates[0]["afmt"]  # H2M
    assert "{{MeaningES}}" not in back
    assert "{{MeaningFR}}" in back
    assert "{{SynonymsFR}}" in back
    assert "{{DictionaryMeaningFR}}" in back


def test_every_front_asks_something_different(model):
    """Two card types with the same front would be indistinguishable in a
    review: the student couldn't tell what is being asked."""
    for a, b in itertools.combinations(model.templates, 2):
        assert a["qfmt"] != b["qfmt"], (a["name"], b["name"])


@pytest.mark.parametrize("name", ["M2H", "PM2H", "P2H"])
def test_hanzi_answers_are_drawn_stroke_by_stroke(model, name):
    template = _templates(model)[name]
    assert "hanziQuizBox" in template["qfmt"]
    assert "HANZI_DATA" in template["qfmt"]
    assert "hanziAnswerBox" in template["afmt"]


@pytest.mark.parametrize("name", ["H2P", "M2P", "HM2P"])
def test_pinyin_answers_are_typed(model, name):
    template = _templates(model)[name]
    assert "{{type:Pinyin}}" in template["qfmt"]
    assert "{{type:Pinyin}}" in template["afmt"]
    # Tone marks and tone numbers are both accepted (pinyin_check include).
    assert "àihào / ai4hao4" in template["qfmt"]
    assert 'id="pinyinCheck"' in template["afmt"]
    assert "{{PinyinNumbered}}" in template["afmt"]


def test_hidden_content_always_has_an_unhide_button(model):
    for template in model.templates:
        for side in ("qfmt", "afmt"):
            html = template[side]
            if any(cls in html for cls in TOGGLED_CLASSES):
                assert "controlHide" in html, (template["name"], side)


def test_every_answer_shows_the_level_badge(model):
    for template in model.templates:
        answer = template["afmt"]
        if answer.strip() == "{{FrontSide}}":
            answer = template["qfmt"]
        assert 'class="levelBadge"' in answer, template["name"]


def test_headwords_are_shown_in_simplified(model):
    """Traditional characters only appear, labelled, on the reference card."""
    for template in model.templates:
        if template["name"] == "Toda la información":
            continue
        assert "{{Traditional}}" not in template["qfmt"] + template["afmt"], template["name"]


def test_note_guid_prefers_the_frozen_guid():
    assert note_guid("你好", "nǐ hǎo", "hello", frozen="abc123") == "abc123"


def test_note_guid_fallback_depends_only_on_the_word_identity():
    guid = note_guid("生", "shēng", "raw, uncooked")
    assert guid == genanki.guid_for("生", "shēng", "raw, uncooked")
    assert guid != note_guid("生", "shēng", "to give birth")


def _write_minimal_output_tsv(tmp_path, **overrides):
    row = {col: "" for col in OUTPUT_COLUMNS + [GUID_COL]}
    row.update({"Simplified": "你好", "Pinyin": "nǐ hǎo", "Meaning": "hello"})
    row.update(overrides)
    input_tsv = tmp_path / "output.tsv"
    pd.DataFrame([row]).to_csv(input_tsv, sep="\t", index=False)
    return input_tsv


def _read_apkg(path):
    with zipfile.ZipFile(path) as z:
        compress_type = z.getinfo("collection.anki2").compress_type
        db = path.parent / f"{path.stem}.anki2"
        db.write_bytes(z.read("collection.anki2"))
    con = sqlite3.connect(db)
    model = next(iter(json.loads(con.execute("select models from col").fetchone()[0]).values()))
    names = [f["name"] for f in model["flds"]]
    notes = {guid: dict(zip(names, flds.split("\x1f")))
             for guid, flds in con.execute("select guid, flds from notes")}
    con.close()
    return notes, compress_type


def test_build_deck_writes_a_compressed_apkg(tmp_path):
    input_tsv = _write_minimal_output_tsv(tmp_path)
    output_apkg = tmp_path / "deck.apkg"
    build_deck(input_tsv, output_apkg)

    # A real deck.apkg (library + embedded stroke data + a note) is at least
    # a few hundred KB; a near-empty file would mean something got dropped.
    assert output_apkg.stat().st_size > 100_000
    _, compress_type = _read_apkg(output_apkg)
    assert compress_type == zipfile.ZIP_DEFLATED


def test_build_deck_uses_the_frozen_guid(tmp_path):
    input_tsv = _write_minimal_output_tsv(tmp_path, Guid="frozen-guid")
    output_apkg = tmp_path / "deck.apkg"
    build_deck(input_tsv, output_apkg)

    notes, _ = _read_apkg(output_apkg)
    assert list(notes) == ["frozen-guid"]


def test_build_deck_fills_source_level_from_the_level(tmp_path):
    input_tsv = _write_minimal_output_tsv(tmp_path)
    output_apkg = tmp_path / "deck.apkg"
    build_deck(input_tsv, output_apkg, level="HSK3")

    notes, _ = _read_apkg(output_apkg)
    assert [n["SourceLevel"] for n in notes.values()] == ["HSK3"]


def test_build_deck_rejects_a_stale_output_tsv(tmp_path):
    """An output.tsv from an older version (different columns) would ship a
    note type that doesn't match the other levels' decks."""
    stale = tmp_path / "output.tsv"
    pd.DataFrame([{col: "" for col in OUTPUT_COLUMNS[:-1]}]).to_csv(stale, sep="\t", index=False)
    with pytest.raises(SystemExit):
        build_deck(stale, tmp_path / "deck.apkg")


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
