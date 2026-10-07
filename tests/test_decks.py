"""Checks on the published decks/*.apkg against the sources they're built from.

Every level shares one note type, so a deck built from older templates or an
older output.tsv would overwrite the newer note type when imported next to
the others. These tests fail when decks/ is out of date: rebuild with
`zhongwen-anki-build-all`.
"""
import json
import re
import sqlite3
import zipfile

import pandas as pd
import pytest

from zhongwen_anki.build_all import DECKS_DIR
from zhongwen_anki.build_deck import build_model
from zhongwen_anki.enrich import DEDUP_KEY, GUID_COL, OUTPUT_COLUMNS
from zhongwen_anki.hanzi_writer import discover_input_tsvs

LEVEL_INPUTS = {tsv.parent.name.upper(): tsv for tsv in discover_input_tsvs()}


@pytest.fixture(scope="module")
def expected_model():
    return build_model(OUTPUT_COLUMNS)


def _read_apkg(path, tmp_path):
    db = tmp_path / f"{path.stem}.anki2"
    with zipfile.ZipFile(path) as z:
        db.write_bytes(z.read("collection.anki2"))
    con = sqlite3.connect(db)
    model = next(iter(json.loads(con.execute("select models from col").fetchone()[0]).values()))
    guids = [row[0] for row in con.execute("select guid from notes")]
    con.close()
    return model, guids


@pytest.mark.parametrize("level", sorted(LEVEL_INPUTS))
def test_published_deck_matches_its_sources(level, expected_model, tmp_path):
    deck = DECKS_DIR / f"{level}.apkg"
    assert deck.exists(), f"{deck} missing: run zhongwen-anki-build-all"
    model, guids = _read_apkg(deck, tmp_path)

    assert [f["name"] for f in model["flds"]] == [f["name"] for f in expected_model.fields]
    assert model["css"] == expected_model.css
    built = [(t["name"], t["qfmt"], t["afmt"]) for t in model["tmpls"]]
    expected = [(t["name"], t["qfmt"], t["afmt"]) for t in expected_model.templates]
    assert built == expected, f"{deck} was built from older templates: run zhongwen-anki-build-all"

    words = pd.read_csv(LEVEL_INPUTS[level], sep="\t", dtype=str).fillna("")
    assert sorted(guids) == sorted(words[GUID_COL]), f"{deck} notes don't match {LEVEL_INPUTS[level]}"


@pytest.mark.parametrize("level", sorted(LEVEL_INPUTS))
def test_every_word_has_a_unique_frozen_guid(level):
    """Published notes keep their GUID forever, so reimports update them
    instead of creating duplicates (see build_deck.note_guid)."""
    words = pd.read_csv(LEVEL_INPUTS[level], sep="\t", dtype=str).fillna("")
    assert (words[GUID_COL] != "").all()
    assert words[GUID_COL].is_unique
    assert not words.duplicated(DEDUP_KEY).any()


def _meaning_parts(meaning):
    """"station; to stand" and "to stand; station" are the same meaning."""
    return frozenset(part.strip().lower() for part in re.split(r"[;,/]", meaning) if part.strip())


def test_no_level_repeats_a_word_from_an_earlier_level():
    """Every answer shows SourceLevel, filled with the deck's level, as the
    level the word was introduced in. That only holds if no level repeats a
    word of an earlier one. The same characters with another reading or
    sense are a different word (还 hái / huán, 站 "station" / "to stand")."""
    seen = {}
    for level in sorted(LEVEL_INPUTS, key=lambda name: int(re.sub(r"\D", "", name) or 0)):
        words = pd.read_csv(LEVEL_INPUTS[level], sep="\t", dtype=str).fillna("")
        keys = [(w.Simplified, w.Pinyin, _meaning_parts(w.Meaning)) for w in words.itertuples()]
        repeated = [f"{k[0]} ({k[1]}) already in {seen[k]}" for k in keys if k in seen]
        assert repeated == [], level
        seen.update({k: level for k in keys})
