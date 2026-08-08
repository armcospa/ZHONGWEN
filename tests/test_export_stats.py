import csv
import json
import sqlite3

import pytest

from zhongwen_anki import export_stats


def _make_modern_collection(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE col (id INTEGER)")
    con.execute("INSERT INTO col (id) VALUES (1)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'Chino - HSK1 (3.0, 2026)')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello')")
    con.execute("CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER)")
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 1)")
    con.commit()
    con.close()


def _make_legacy_collection(path):
    con = sqlite3.connect(path)
    decks_json = json.dumps({"1": {"name": "Legacy Deck"}})
    con.execute("CREATE TABLE col (decks TEXT)")
    con.execute("INSERT INTO col (decks) VALUES (?)", (decks_json,))
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello')")
    con.execute("CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER)")
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 1, -600, -600, 0, 3000, 0)")
    con.commit()
    con.close()


def _make_collection_with_card_in_filtered_deck(path):
    """A card whose home deck is 1 but is currently sitting in filtered deck 2."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE col (id INTEGER)")
    con.execute("INSERT INTO col (id) VALUES (1)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'Chino - HSK1 (3.0, 2026)')")
    con.execute("INSERT INTO decks VALUES (2, 'Repaso Pinyin (filtrado)')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello')")
    con.execute("CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER)")
    con.execute("INSERT INTO cards VALUES (200, 100, 2, 1)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 1)")
    con.commit()
    con.close()


def test_export_modern_schema(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_modern_collection(collection)
    output = tmp_path / "out.csv"

    export_stats.export(collection, output, deck_filter=None)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    row = rows[0]
    assert row["deck"] == "Chino - HSK1 (3.0, 2026)"
    assert row["word"] == "你好"
    assert row["ease_label"] == "Good"
    assert row["is_correct"] == "1"
    assert row["ease_factor_percent"] == "250.0"
    assert row["time_seconds"] == "5.0"
    assert row["review_type"] == "review"


def test_export_deck_filter_excludes_non_matching_decks(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_modern_collection(collection)
    output = tmp_path / "out.csv"

    export_stats.export(collection, output, deck_filter="nonexistent")

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows == []


def test_export_legacy_schema_fallback(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_legacy_collection(collection)
    output = tmp_path / "out.csv"

    export_stats.export(collection, output, deck_filter=None)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    row = rows[0]
    assert row["deck"] == "Legacy Deck"
    assert row["ease_label"] == "Again"
    assert row["is_correct"] == "0"
    assert row["interval"] == "-600"


def test_export_attributes_reviews_to_the_home_deck_not_the_filtered_deck(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_collection_with_card_in_filtered_deck(collection)
    output = tmp_path / "out.csv"

    export_stats.export(collection, output, deck_filter=None)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["deck"] == "Chino - HSK1 (3.0, 2026)"


def test_find_collection_raises_for_missing_explicit_path(tmp_path):
    missing = tmp_path / "nope.anki2"
    with pytest.raises(SystemExit):
        export_stats._find_collection(missing)


def test_find_collection_returns_existing_explicit_path(tmp_path):
    path = tmp_path / "collection.anki2"
    path.write_text("")
    assert export_stats._find_collection(path) == path
