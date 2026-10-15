"""Tests for zhongwen_anki.export_stats."""
import argparse
import csv
import json
import sqlite3
import tempfile
import zipfile

import pytest

from zhongwen_anki import export_stats


@pytest.fixture(autouse=True)
def _isolated_tempdir(tmp_path, monkeypatch):
    """Keep .colpkg extractions inside tmp_path.

    Tests call _extract_colpkg_to_sqlite directly, which (unlike main())
    leaves the cleanup to the caller; without this every run would leave
    anki_colpkg_* folders in the system temp directory.
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))


# --- Fixtures to create test SQLite databases ---


def _make_modern_collection(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
    con.execute("INSERT INTO col VALUES (1, 1577836800)")  # crt in seconds since epoch
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'Chino - HSK1 (3.0, 2026)')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello', ' HSK1 leech ', 'D_goq7CnLD')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER)"
    )
    # due=2527 means ~2527 days after col.crt (2020-01-01) ≈ 2026-10-09
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 2, 2527, 4, 2500, 1, 2, 0)")
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
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello', '', '')")
    con.execute("CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER)")
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 2)")
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
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello', '', '')")
    con.execute("CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER)")
    con.execute("INSERT INTO cards VALUES (200, 100, 2, 1, 0)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 1)")
    con.commit()
    con.close()


def _make_collection_with_multiple_reviews(path):
    """Collection with multiple reviews for --since testing."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE col (id INTEGER)")
    con.execute("INSERT INTO col (id) VALUES (1)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'Chino - HSK1 (3.0, 2026)')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello', ' HSK1 ', 'GUID1')")
    con.execute("INSERT INTO notes VALUES (101, '世界\x1fworld', ' HSK1 ', 'GUID2')")
    con.execute("CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER)")
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0)")
    con.execute("INSERT INTO cards VALUES (201, 101, 1, 0, 2)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    # 3 reviews on different dates
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 1)")  # 2025-01-01
    con.execute("INSERT INTO revlog VALUES (1735776000000, 200, 1, -600, 4, 0, 3000, 0)")  # 2025-01-02
    con.execute("INSERT INTO revlog VALUES (1735862400000, 201, 4, 10, 4, 2600, 2000, 1)")  # 2025-01-03
    con.commit()
    con.close()


# --- Backwards compatibility: export() alias ---


def test_export_modern_schema(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_modern_collection(collection)
    output = tmp_path / "out.csv"

    export_stats.export(collection, output, deck_filter=None)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    row = rows[0]
    assert row["deck"] == "Chino - HSK1 (3.0, 2026)"
    assert row["current_filtered_deck"] == ""
    assert row["word"] == "你好"
    assert row["card_type"] == "H2P"
    assert row["tags"] == "HSK1 leech"
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
    assert rows[0]["current_filtered_deck"] == "Repaso Pinyin (filtrado)"


def test_export_maps_card_ord_to_card_type(tmp_path):
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER)")
    con.execute("INSERT INTO col (id) VALUES (1)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'Chino - HSK1 (3.0, 2026)')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello', '', '')")
    con.execute("CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER)")
    con.execute("CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
                 "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)")
    for i, ord_ in enumerate([0, 1, 2, 3, 99]):
        card_id, review_id = 200 + i, 1735689600000 + i
        con.execute("INSERT INTO cards VALUES (?, 100, 1, 0, ?)", (card_id, ord_))
        con.execute("INSERT INTO revlog VALUES (?, ?, 3, 4, 1, 2500, 5000, 1)", (review_id, card_id))
    con.commit()
    con.close()
    output = tmp_path / "out.csv"

    export_stats.export(collection, output, deck_filter=None)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert [row["card_type"] for row in rows] == [
        "H2M", "M2H", "H2P", "PM2H", "(ord 99)",
    ]


# --- New functionality: --since ---


def test_export_since_filters_reviews(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_collection_with_multiple_reviews(collection)
    output = tmp_path / "out.csv"

    # Only reviews since 2025-01-02 (middle review)
    written = export_stats.export_reviews(collection, output, since="2025-01-02")

    assert written == 2
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 2


def test_export_since_all(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_collection_with_multiple_reviews(collection)
    output = tmp_path / "out.csv"

    written = export_stats.export_reviews(collection, output, since="2024-01-01")

    assert written == 3


def test_export_since_future_date(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_collection_with_multiple_reviews(collection)
    output = tmp_path / "out.csv"

    written = export_stats.export_reviews(collection, output, since="2026-01-01")

    assert written == 0


# --- New functionality: vocab enrichment ---


def test_export_reviews_with_vocab_enrichment(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_modern_collection(collection)
    output = tmp_path / "out.csv"

    # Create a fake vocab directory
    vocab_dir = tmp_path / "data" / "hsk1"
    vocab_dir.mkdir(parents=True)
    tsv = vocab_dir / "input.tsv"
    tsv.write_text(
        "Simplified\tPinyin\tMeaning\tMeaningES\tGuid\n"
        "你好\tnǐ hão\thello\thola\tD_goq7CnLD\n",
        encoding="utf-8",
    )

    export_stats.export_reviews(collection, output, vocab_dir=tmp_path / "data")

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    row = rows[0]
    assert row["pinyin"] == "nǐ hão"
    assert row["meaning"] == "hello"
    assert row["meaning_es"] == "hola"


def test_export_reviews_without_vocab_has_no_extra_columns(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_modern_collection(collection)
    output = tmp_path / "out.csv"

    export_stats.export_reviews(collection, output, vocab_dir=None)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    header = list(rows[0].keys())
    assert "pinyin" not in header
    assert "meaning" not in header


# --- New functionality: card snapshot ---


def test_export_card_snapshot(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_modern_collection(collection)
    output = tmp_path / "cards.csv"

    written = export_stats.export_card_snapshot(collection, output)

    assert written == 1
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    row = rows[0]
    assert row["word"] == "你好"
    assert row["card_type"] == "H2P"


def test_export_card_snapshot_deck_filter(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_modern_collection(collection)
    output = tmp_path / "cards.csv"

    written = export_stats.export_card_snapshot(collection, output, deck_filter="nonexistent")

    assert written == 0


# --- Collection discovery ---


def test_find_collection_raises_for_missing_explicit_path(tmp_path):
    missing = tmp_path / "nope.anki2"
    with pytest.raises(SystemExit):
        export_stats._find_collection(missing)


def test_find_collection_returns_existing_explicit_path(tmp_path):
    path = tmp_path / "collection.anki2"
    path.write_text("")
    assert export_stats._find_collection(path) == path


# --- Type=4 / ease=0 handling ---


def test_export_type4_ease0_is_correct_empty(tmp_path):
    """Type=4 (manual) with any ease: is_correct should be empty, is_user_answer False."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER)")
    con.execute("INSERT INTO col (id) VALUES (1)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '测试\x1ftest', '', 'GUID_T4')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    # type=4 (manual), ease=0
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 0, 0, 0, 0, 1000, 4)")
    con.commit()
    con.close()

    output = tmp_path / "out.csv"
    export_stats.export_reviews(collection, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["is_correct"] == ""
    assert rows[0]["is_user_answer"] == "False"
    assert rows[0]["review_type"] == "manual"


def test_export_type5_is_correct_empty(tmp_path):
    """Type=5 (rescheduled): is_correct should be empty, is_user_answer False."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER)")
    con.execute("INSERT INTO col (id) VALUES (1)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '测试\x1ftest', '', 'GUID_T5')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    # type=5 (rescheduled), ease=3
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 5)")
    con.commit()
    con.close()

    output = tmp_path / "out.csv"
    export_stats.export_reviews(collection, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["is_correct"] == ""
    assert rows[0]["is_user_answer"] == "False"
    assert rows[0]["review_type"] == "rescheduled"


# --- QUEUE_LABELS and TYPE_LABELS ---


def test_queue_labels_correctness():
    """Verify QUEUE_LABELS mapping is correct."""
    assert export_stats.QUEUE_LABELS[-3] == "buried/user"
    assert export_stats.QUEUE_LABELS[-2] == "buried/scheduler"
    assert export_stats.QUEUE_LABELS[-1] == "suspended"
    assert export_stats.QUEUE_LABELS[0] == "new"
    assert export_stats.QUEUE_LABELS[1] == "learning"
    assert export_stats.QUEUE_LABELS[2] == "review"
    assert export_stats.QUEUE_LABELS[3] == "relearning"
    assert export_stats.QUEUE_LABELS[4] == "preview"


def test_type_labels_correctness():
    """Verify TYPE_LABELS mapping is correct."""
    assert export_stats.TYPE_LABELS[0] == "new"
    assert export_stats.TYPE_LABELS[1] == "learning"
    assert export_stats.TYPE_LABELS[2] == "review"
    assert export_stats.TYPE_LABELS[3] == "relearning"


# --- due_date calculation ---


def test_calculate_due_date_review_card():
    """Review cards (queue=2, type=2): due is day number from collection creation."""
    col_crt = 1577836800.0  # 2020-01-01T00:00:00Z
    # due=88 means 88 days after day0 (col_crt - rollover_hour, in creation tz).
    # creation_offset_min=0 makes this deterministic regardless of machine timezone:
    # day0 = 2020-01-01T00:00Z - 4h = 2019-12-31; +88 days = 2020-03-28
    due_date = export_stats._calculate_due_date(
        due=88, queue=2, card_type=2, odue=0, col_crt=col_crt, is_filtered=False,
        creation_offset_min=0,
    )
    assert due_date == "2020-03-28"


def test_calculate_due_date_review_card_with_creation_offset():
    """Regression (real collection): day 0 must be computed in the creation timezone.

    col.crt=1783540800, config.creationOffset=-480 (created in UTC+8),
    rollover=4. A review card with due=88 is scheduled by Anki for
    2026-10-05; the old local-time formula gave 2026-10-04 (one day early).
    """
    due_date = export_stats._calculate_due_date(
        due=88, queue=2, card_type=2, odue=0,
        col_crt=1783540800.0, is_filtered=False,
        rollover_hour=4, creation_offset_min=-480,
    )
    assert due_date == "2026-10-05"


def test_calculate_due_date_new_card():
    """New cards (queue=0): due is order, so due_date should be empty."""
    col_crt = 1577836800.0
    due_date = export_stats._calculate_due_date(
        due=5, queue=0, card_type=0, odue=0, col_crt=col_crt, is_filtered=False
    )
    assert due_date == ""


def test_calculate_due_date_suspended_card():
    """Suspended cards (queue=-1): no due date."""
    col_crt = 1577836800.0
    due_date = export_stats._calculate_due_date(
        due=20261015, queue=-1, card_type=2, odue=0, col_crt=col_crt, is_filtered=False
    )
    assert due_date == ""


def test_calculate_due_date_learning_card():
    """Learning cards (queue=1): due is epoch seconds (absolute)."""
    col_crt = 1577836800.0
    # due=1735689600 is 2025-01-01T00:00:00Z as epoch seconds
    due_date = export_stats._calculate_due_date(
        due=1735689600, queue=1, card_type=1, odue=0, col_crt=col_crt, is_filtered=False
    )
    assert due_date == "2025-01-01"


def test_calculate_due_date_filtered_card_with_odue():
    """Filtered deck cards: use odue (day number) when available."""
    col_crt = 1577836800.0  # 2020-01-01T00:00:00Z
    # due is -100000+pos (meaningless), odue=50 (day number)
    # creation_offset_min=0 keeps the expectation independent of machine timezone:
    # day0 = 2019-12-31; +50 days = 2020-02-19
    due_date = export_stats._calculate_due_date(
        due=-99701, queue=1, card_type=2, odue=50, col_crt=col_crt, is_filtered=True,
        creation_offset_min=0,
    )
    assert due_date == "2020-02-19"


# --- FSRS data extraction ---


def test_export_card_snapshot_fsrs_data(tmp_path):
    """FSRS stability and difficulty extracted from cards.data JSON (keys 's' and 'd')."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
    con.execute("INSERT INTO col VALUES (1, 1783540800)")  # seconds, not ms
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '测试\x1ftest', '', 'GUID_FSRS')")
    con.execute(
        "CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, did INTEGER, odid INTEGER, "
        "ord INTEGER, due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, "
        "queue INTEGER, type INTEGER, odue INTEGER, reps INTEGER, data TEXT)"
    )
    # Anki uses keys 's' (stability) and 'd' (difficulty)
    fsrs_data = json.dumps({"s": 1.234, "d": 2.567, "lrt": 1791108888, "pos": 0})
    con.execute(
        "INSERT INTO cards (id, nid, did, odid, ord, due, ivl, factor, lapses, queue, type, odue, reps, data) "
        "VALUES (200, 100, 1, 0, 0, 88, 4, 2500, 0, 2, 2, 0, 10, ?)",
        (fsrs_data,)
    )
    con.commit()
    con.close()

    output = tmp_path / "cards.csv"
    export_stats.export_card_snapshot(collection, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["fsrs_stability"] == "1.234", f"Got: {rows[0].get('fsrs_stability')}"
    assert rows[0]["fsrs_difficulty"] == "2.567", f"Got: {rows[0].get('fsrs_difficulty')}"


def test_export_card_snapshot_no_fsrs_data(tmp_path):
    """Cards without data field should have empty FSRS columns."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
    con.execute("INSERT INTO col VALUES (1, 1577836800)")  # crt in seconds since epoch
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '测试\x1ftest', '', 'GUID_NOFSRS')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER, "
        "odue INTEGER, reps INTEGER, data TEXT)"
    )
    con.execute(
        "INSERT INTO cards (id, nid, did, odid, ord, due, ivl, factor, lapses, queue, type, odue, reps, data) "
        "VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0, 0, 5, '')"
    )
    con.commit()
    con.close()

    output = tmp_path / "cards.csv"
    export_stats.export_card_snapshot(collection, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows[0]["fsrs_stability"] == ""
    assert rows[0]["fsrs_difficulty"] == ""


# --- .colpkg support ---


def test_colpkg_opening_as_zip(tmp_path):
    """Test that .colpkg files are opened as ZIP archives."""
    # Create a minimal colpkg: ZIP containing an anki21 file (SQLite)
    colpkg_path = tmp_path / "collection.colpkg"
    # Create the inner SQLite first
    inner_db = tmp_path / "anki21"
    con = sqlite3.connect(inner_db)
    con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
    con.execute("INSERT INTO col VALUES (1, 1577836800000)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '测试\x1ftest', '', 'GUID_COLPKG')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER, "
        "odue INTEGER, reps INTEGER, data TEXT)"
    )
    con.execute(
        "INSERT INTO cards (id, nid, did, odid, ord, due, ivl, factor, lapses, queue, type, odue, reps, data) "
        "VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0, 0, 5, '')"
    )
    con.commit()
    con.close()

    # Package into ZIP as colpkg
    with zipfile.ZipFile(colpkg_path, "w") as zf:
        zf.write(inner_db, "anki21")

    # Now extract via our function
    extracted = export_stats._extract_colpkg_to_sqlite(colpkg_path)
    assert extracted.exists()
    # Verify extracted SQLite is valid
    check_con = sqlite3.connect(str(extracted))
    deck_name = check_con.execute("SELECT name FROM decks WHERE id=1").fetchone()[0]
    assert deck_name == "HSK1"
    check_con.close()


def test_colpkg_priority_selection_logic(tmp_path):
    """Verify priority selection: anki21b > anki21 > anki2 by checking file selection logic.

    We test the priority by creating a colpkg with only anki21 (not anki21b),
    and verifying it picks anki21 over anki2.
    """
    colpkg_path = tmp_path / "collection.colpkg"
    # Create minimal SQLite for anki2 and anki21
    for name in ("anki2", "anki21"):
        db_path = tmp_path / name
        con = sqlite3.connect(db_path)
        con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
        con.execute("INSERT INTO col VALUES (1, 1577836800000)")
        con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
        con.execute("INSERT INTO decks VALUES (1, 'Chosen')")
        con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
        con.execute("INSERT INTO notes VALUES (100, 'test', '', '')")
        con.execute(
            "CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, did INTEGER, odid INTEGER, "
            "ord INTEGER, due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, "
            "queue INTEGER, type INTEGER, odue INTEGER, reps INTEGER, data TEXT)"
        )
        con.commit()
        con.close()

    with zipfile.ZipFile(colpkg_path, "w") as zf:
        zf.write(tmp_path / "anki2", "anki2")
        zf.write(tmp_path / "anki21", "anki21")

    # Extract -- should pick anki21 (priority over anki2)
    extracted = export_stats._extract_colpkg_to_sqlite(colpkg_path)
    assert extracted.exists()
    check_con = sqlite3.connect(str(extracted))
    deck_name = check_con.execute("SELECT name FROM decks WHERE id=1").fetchone()[0]
    assert deck_name == "Chosen"
    check_con.close()


# --- is_user_answer column logic ---


def test_is_user_answer_true_for_normal_review(tmp_path):
    """is_user_answer=True when ease >= 1 AND type NOT IN (4, 5)."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER)")
    con.execute("INSERT INTO col (id) VALUES (1)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '测试\x1ftest', '', 'GUID_USER')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    # Normal review: ease=3, type=1
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 1)")
    con.commit()
    con.close()

    output = tmp_path / "out.csv"
    export_stats.export_reviews(collection, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows[0]["is_user_answer"] == "True"


def test_is_user_answer_false_for_manual(tmp_path):
    """is_user_answer=False when type=4 even with valid ease."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER)")
    con.execute("INSERT INTO col (id) VALUES (1)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '测试\x1ftest', '', 'GUID_MANUAL')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    # Manual reschedule: ease=3, type=4
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 4)")
    con.commit()
    con.close()

    output = tmp_path / "out.csv"
    export_stats.export_reviews(collection, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows[0]["is_user_answer"] == "False"


# --- --since date validation ---


def test_validate_since_valid_date():
    """Valid date format passes validation."""
    result = export_stats._validate_since("2025-01-15")
    assert result == "2025-01-15"


def test_validate_since_invalid_format():
    """Invalid date format raises argparse.ArgumentTypeError."""
    with pytest.raises(argparse.ArgumentTypeError, match="Invalid date format"):
        export_stats._validate_since("01-15-2025")


def test_validate_since_non_date_string():
    """Non-date string raises argparse.ArgumentTypeError."""
    with pytest.raises(argparse.ArgumentTypeError):
        export_stats._validate_since("not a date")


# --- NO gravlog references ---


def test_no_gravlog_references_in_module():
    """Verify no gravlog references exist in export_stats module."""
    import inspect
    source = inspect.getsource(export_stats)
    assert "gravlog" not in source.lower()


# --- reps column present ---


def test_reps_column_present_in_card_snapshot(tmp_path):
    """Verify reps column is present in card snapshot CSV."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
    con.execute("INSERT INTO col VALUES (1, 1577836800)")  # crt in seconds since epoch
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '测试\x1ftest', '', 'GUID_REPS')")
    # Match Anki column order: id, nid, guid, did, odom, ... queue, type, dv, csum, flags, due, ibl, ib2, ib3, ivl, lastIvl, lapsed, lapses, left, odue, rep, due2, tag, data
    # Use a simplified version with just the columns export_card_snapshot needs
    con.execute(
        "CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, did INTEGER, odid INTEGER, "
        "ord INTEGER, due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, "
        "queue INTEGER, type INTEGER, odue INTEGER, reps INTEGER, data TEXT)"
    )
    # Named column insert to avoid order issues
    con.execute(
        "INSERT INTO cards (id, nid, did, odid, ord, due, ivl, factor, lapses, queue, type, odue, reps, data) "
        "VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0, 0, 42, '')"
    )
    con.commit()
    con.close()

    output = tmp_path / "cards.csv"
    export_stats.export_card_snapshot(collection, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    header = list(rows[0].keys())
    assert "reps" in header
    assert rows[0]["reps"] == "42", f"Got reps={rows[0]['reps']}"


# --- ease_factor_percent empty for new cards / factor==0 ---


def test_ease_factor_percent_empty_for_factor_zero(tmp_path):
    """ease_factor_percent should be empty when factor == 0 (new cards)."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER)")
    con.execute("INSERT INTO col (id) VALUES (1)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '测试\x1ftest', '', 'GUID_NEW')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0, 5, 0, 0, 0, 0, 0)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    # New card review with factor=0
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 1, 0, 0, 5000, 0)")
    con.commit()
    con.close()

    output = tmp_path / "out.csv"
    export_stats.export_reviews(collection, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows[0]["ease_factor_percent"] == ""


def test_ease_factor_percent_empty_in_card_snapshot_for_factor_zero(tmp_path):
    """Card snapshot: ease_factor_percent empty when factor == 0."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
    con.execute("INSERT INTO col VALUES (1, 1577836800000)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '测试\x1ftest', '', 'GUID_NEWCARD')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER, "
        "odue INTEGER, reps INTEGER, data TEXT)"
    )
    # New card with factor=0
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0, 5, 0, 0, 0, 0, 0, 0, 0, '')")
    con.commit()
    con.close()

    output = tmp_path / "cards.csv"
    export_stats.export_card_snapshot(collection, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows[0]["ease_factor_percent"] == ""


# --- Phase D: colpkg zstd, dummy detection, review_id, --append, rollover ---


def test_colpkg_with_anki21b_zstd_decompression(tmp_path):
    """.colpkg with collection.anki21b (zstd compressed, no content size) extracts correctly."""
    import zstandard as zstd

    # Create the inner SQLite database
    inner_db = tmp_path / "temp.db"
    con = sqlite3.connect(inner_db)
    con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
    con.execute("INSERT INTO col VALUES (1, 1577836800)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'ZstdDeck')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello', '', 'GUID_ZSTD')")
    con.execute(
        "CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, did INTEGER, odid INTEGER, "
        "ord INTEGER, due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, "
        "queue INTEGER, type INTEGER, odue INTEGER, reps INTEGER, data TEXT)"
    )
    con.execute(
        "INSERT INTO cards (id, nid, did, odid, ord, due, ivl, factor, lapses, queue, type, odue, reps, data) "
        "VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0, 0, 5, '')"
    )
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 1)")
    con.commit()
    con.close()

    # Compress with zstd streaming compressor (no content size in frame header)
    compressed_db = tmp_path / "collection.anki21b"
    with inner_db.open("rb") as infile, compressed_db.open("wb") as outfile:
        with zstd.ZstdCompressor().stream_writer(outfile) as compressor:
            compressor.write(infile.read())

    # Package into ZIP as colpkg
    colpkg_path = tmp_path / "collection.colpkg"
    with zipfile.ZipFile(colpkg_path, "w") as zf:
        zf.write(compressed_db, "collection.anki21b")

    # Extract and verify
    extracted = export_stats._extract_colpkg_to_sqlite(colpkg_path)
    assert extracted.exists()
    check_con = sqlite3.connect(str(extracted))
    deck_name = check_con.execute("SELECT name FROM decks WHERE id=1").fetchone()[0]
    assert deck_name == "ZstdDeck"
    count = check_con.execute("SELECT COUNT(*) FROM revlog").fetchone()[0]
    assert count == 1
    check_con.close()


def test_colpkg_dummy_legacy_only_raises_system_exit(tmp_path):
    """.colpkg with only collection.anki2 and empty revlog raises SystemExit."""
    # Create a legacy-only SQLite with empty revlog
    inner_db = tmp_path / "collection.anki2"
    con = sqlite3.connect(inner_db)
    con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
    con.execute("INSERT INTO col VALUES (1, 1577836800)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    # revlog is empty
    con.commit()
    con.close()

    # Package into ZIP
    colpkg_path = tmp_path / "collection.colpkg"
    with zipfile.ZipFile(colpkg_path, "w") as zf:
        zf.write(inner_db, "collection.anki2")

    with pytest.raises(SystemExit, match="legacy-compatibility"):
        export_stats._extract_colpkg_to_sqlite(colpkg_path)


def test_review_id_equals_revlog_id_and_is_first_column(tmp_path):
    """review_id column is present, equals revlog.id, and is the first column."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER)")
    con.execute("INSERT INTO col (id) VALUES (1)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello', '', '')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 1)")
    con.commit()
    con.close()

    output = tmp_path / "out.csv"
    export_stats.export_reviews(collection, output)

    with output.open(encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        row = next(reader)
        # First column is review_id
        assert header[0] == "review_id"
        # review_id equals revlog.id
        assert row[0] == "1735689600000"


def test_append_no_duplicates_and_adds_only_new(tmp_path):
    """Two consecutive exports with --append produce no duplicates; second adds only new rows."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER)")
    con.execute("INSERT INTO col (id) VALUES (1)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello', '', '')")
    con.execute("INSERT INTO notes VALUES (101, '世界\x1fworld', '', '')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0)")
    con.execute("INSERT INTO cards VALUES (201, 101, 1, 0, 0, 2527, 4, 2500, 0, 2, 0)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 1)")
    con.execute("INSERT INTO revlog VALUES (1735776000000, 201, 2, 3, 1, 2500, 3000, 1)")
    con.commit()
    con.close()

    output = tmp_path / "reviews.csv"

    # First export (normal, no append): exports both rows
    count1 = export_stats.export_reviews(collection, output)
    assert count1 == 2

    rows_after_first = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows_after_first) == 2

    # Second export with append: no new rows (all already present)
    count2 = export_stats.export_reviews(collection, output, append=True)
    assert count2 == 0

    rows_after_second = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows_after_second) == 2, "Should still have exactly 2 rows (no duplicates)"


def test_append_with_different_header_raises_system_exit(tmp_path):
    """Appending to a CSV with a different header raises SystemExit."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER)")
    con.execute("INSERT INTO col (id) VALUES (1)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'HSK1')")
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello', '', '')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 1)")
    con.commit()
    con.close()

    output = tmp_path / "reviews.csv"
    # Write a CSV with wrong headers
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["wrong_header", "another_header"])
        writer.writerow(["123", "456"])

    with pytest.raises(SystemExit, match="does not match"):
        export_stats.export_reviews(collection, output, append=True)


def test_get_rollover_hour_default():
    """_get_rollover_hour returns 4 when config table is missing."""
    con = sqlite3.connect(":memory:")
    result = export_stats._get_rollover_hour(con)
    con.close()
    assert result == 4


def test_get_rollover_hour_from_config():
    """_get_rollover_hour reads rollover from the config table (real Anki format).

    Anki stores one row per key with the value as a JSON blob
    (e.g. ('rollover', '6')), not a single 'config' row.
    """
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE config (key TEXT, val TEXT)")
    con.execute("INSERT INTO config VALUES (?, ?)", ("rollover", b"6"))
    result = export_stats._get_rollover_hour(con)
    con.close()
    assert result == 6


def test_get_rollover_hour_missing_rollover_key():
    """_get_rollover_hour returns 4 when the config table has no rollover row."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE config (key TEXT, val TEXT)")
    con.execute("INSERT INTO config VALUES (?, ?)", ("creationOffset", b"-480"))
    result = export_stats._get_rollover_hour(con)
    con.close()
    assert result == 4


def test_get_config_int_missing_table():
    """_get_config_int returns None when the config table does not exist."""
    con = sqlite3.connect(":memory:")
    assert export_stats._get_config_int(con, "rollover") is None
    con.close()


def test_get_config_int_reads_json_blob():
    """_get_config_int parses the JSON blob in the config row."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE config (key TEXT, val TEXT)")
    con.execute("INSERT INTO config VALUES (?, ?)", ("creationOffset", b"-480"))
    assert export_stats._get_config_int(con, "creationOffset") == -480
    assert export_stats._get_config_int(con, "absent") is None
    con.close()


def test_get_config_int_invalid_value():
    """_get_config_int returns None when the stored value is not valid JSON."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE config (key TEXT, val TEXT)")
    con.execute("INSERT INTO config VALUES (?, ?)", ("rollover", "not-json"))
    assert export_stats._get_config_int(con, "rollover") is None
    con.close()


# --- Template name-based card type resolution ---


def test_load_template_map_from_modern_templates_table():
    """_load_template_map reads notetypes + templates tables with unicase collation."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.create_collation("unicase", lambda a, b: (a > b) - (a < b))
    con.execute("CREATE TABLE notetypes (id INTEGER, name TEXT)")
    con.execute("INSERT INTO notetypes VALUES (999, 'Chino - HSK (ES/EN)')")
    con.execute(
        "CREATE TABLE templates ("
        "id INTEGER PRIMARY KEY, ntid INTEGER, did INTEGER, ord INTEGER, "
        "qfmt TEXT, afmt TEXT, name TEXT COLLATE unicase)"
    )
    con.execute("INSERT INTO templates VALUES (1, 999, 0, 0, '', '', 'Hanzi -> Significado')")
    con.execute("INSERT INTO templates VALUES (2, 999, 0, 1, '', '', 'Significado -> Hanzi')")
    con.execute("INSERT INTO templates VALUES (3, 999, 0, 2, '', '', 'Hanzi -> Pinyin')")

    result = export_stats._load_template_map(con)
    con.close()

    assert result == {
        999: {
            "name": "Chino - HSK (ES/EN)",
            "templates": {0: "Hanzi -> Significado", 1: "Significado -> Hanzi", 2: "Hanzi -> Pinyin"},
        },
    }


def test_load_template_map_returns_empty_for_missing_tables():
    """_load_template_map returns {} when the templates table doesn't exist."""
    con = sqlite3.connect(":memory:")
    result = export_stats._load_template_map(con)
    con.close()
    assert result == {}


def test_resolve_card_type_name_based_lookup():
    """_resolve_card_type uses template name from map, not positional ord."""
    template_map = {
        999: {"name": "Chino", "templates": {0: "Hanzi -> Significado", 2: "Hanzi -> Pinyin"}},
    }
    code, template_name, notetype = export_stats._resolve_card_type(0, 999, template_map)
    assert code == "H2M"
    assert template_name == "Hanzi -> Significado"
    assert notetype == "Chino"
    code, template_name, notetype = export_stats._resolve_card_type(2, 999, template_map)
    assert code == "H2P"
    assert template_name == "Hanzi -> Pinyin"
    assert notetype == "Chino"


def test_resolve_card_type_override_takes_precedence():
    """TEMPLATE_OVERRIDES[(notetype, template)] beats CARD_NAME_TO_CODE."""
    template_map = {
        999: {"name": "Chino - HSK (ES/EN)+", "templates": {3: "Pinyin -> Significado"}},
    }
    code, template_name, notetype = export_stats._resolve_card_type(3, 999, template_map)
    assert code == "M2P"  # Override
    assert template_name == "Pinyin -> Significado"
    assert notetype == "Chino - HSK (ES/EN)+"
    # Same template name in a different model resolves to P2M
    template_map2 = {
        998: {"name": "Chino - HSK (ES/EN)", "templates": {3: "Pinyin -> Significado"}},
    }
    code2, template_name2, notetype2 = export_stats._resolve_card_type(3, 998, template_map2)
    assert code2 == "P2M"
    assert template_name2 == "Pinyin -> Significado"
    assert notetype2 == "Chino - HSK (ES/EN)"


def test_resolve_card_type_fallback_to_ord_when_name_unknown():
    """_resolve_card_type returns template name (not positional guess) when name
    is known but not in CARD_NAME_TO_CODE."""
    template_map = {
        999: {"name": "Model", "templates": {0: "Hanzi -> Significado", 5: "Custom Template"}},
    }
    code, name, nt = export_stats._resolve_card_type(0, 999, template_map)
    assert code == "H2M"
    assert name == "Hanzi -> Significado"
    # "Custom Template" not in CARD_NAME_TO_CODE, so return name itself
    code, name, nt = export_stats._resolve_card_type(5, 999, template_map)
    assert code == "Custom Template"
    assert name == "Custom Template"


def test_resolve_card_type_fallback_to_ord_when_no_template_map():
    """_resolve_card_type falls back to CARD_TYPE_BY_ORD with empty template_map."""
    code, name, nt = export_stats._resolve_card_type(0, 999, {})
    assert code == "H2M"
    assert name == ""
    assert nt == ""
    code, name, nt = export_stats._resolve_card_type(3, 999, {})
    assert code == "PM2H"
    assert name == ""
    assert nt == ""
    code, name, nt = export_stats._resolve_card_type(99, 999, {})
    assert code == "(ord 99)"
    assert name == ""
    assert nt == ""


def test_resolve_card_type_ord_10_beyond_standard():
    """_resolve_card_type handles ord 10 (e.g. 'Todas las tarjetas' in + variants).
    When the name maps to a known code, it returns that code regardless of ord."""
    template_map = {
        999: {"name": "Model", "templates": {10: "Toda la información"}},
    }
    code, name, nt = export_stats._resolve_card_type(10, 999, template_map)
    assert code == "Toda la información"
    assert name == "Toda la información"


def test_export_mixed_template_collection_uses_name_lookup(tmp_path):
    """Export correctly resolves card types in a collection with mixed template
    orders (like 'Chino - HSK (ES/EN)+' with 11 templates in a different order).

    This simulates a collection where template ord=0 maps to 'Significado -> Hanzi'
    instead of the default 'Hanzi -> Significado', verifying name-based lookup.
    """
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
    con.execute("INSERT INTO col VALUES (1, 1577836800)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'Chino - HSK (ES/EN)+')")
    # notes table with mid column (note type id)
    con.execute(
        "CREATE TABLE notes (id INTEGER, guid TEXT, mid INTEGER, "
        "flds TEXT, tags TEXT)"
    )
    con.execute("INSERT INTO notes VALUES (100, 'G1', 999, '你好\x1fhello', '')")
    con.execute("INSERT INTO notes VALUES (101, 'G2', 999, '世界\x1fworld', '')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER)"
    )
    # Card with ord=0 in this model is "Significado -> Hanzi" (swapped from default)
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0)")
    # Card with ord=2 in this model is still "Hanzi -> Pinyin"
    con.execute("INSERT INTO cards VALUES (201, 101, 1, 0, 2)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 1)")
    con.execute("INSERT INTO revlog VALUES (1735776000000, 201, 3, 4, 1, 2500, 5000, 1)")

    # notetypes table (required for _load_template_map to get notetype names)
    con.execute("CREATE TABLE notetypes (id INTEGER, name TEXT)")
    con.execute("INSERT INTO notetypes VALUES (999, 'Chino - HSK (ES/EN)')")

    # Modern templates table with swapped order
    con.execute(
        "CREATE TABLE templates ("
        "id INTEGER PRIMARY KEY, ntid INTEGER, ord INTEGER, name TEXT)"
    )
    # ord=0 is now "Significado -> Hanzi" (M2H), not "Hanzi -> Significado"
    con.execute("INSERT INTO templates VALUES (1, 999, 0, 'Significado -> Hanzi')")
    con.execute("INSERT INTO templates VALUES (2, 999, 1, 'Hanzi -> Significado')")
    con.execute("INSERT INTO templates VALUES (3, 999, 2, 'Hanzi -> Pinyin')")
    con.commit()
    con.close()

    output = tmp_path / "out.csv"
    export_stats.export_reviews(collection, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 2
    # With name-based lookup: ord=0 -> "Significado -> Hanzi" -> M2H
    # Old positional mapping would have incorrectly returned H2M
    assert rows[0]["card_type"] == "M2H"
    # ord=2 -> "Hanzi -> Pinyin" -> H2P (same in both systems)
    assert rows[1]["card_type"] == "H2P"


def test_export_card_snapshot_mixed_template_collection(tmp_path):
    """Card snapshot also uses name-based template lookup."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
    con.execute("INSERT INTO col VALUES (1, 1577836800)")
    con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
    con.execute("INSERT INTO decks VALUES (1, 'Chino - HSK (ES/EN)+')")
    con.execute(
        "CREATE TABLE notes (id INTEGER, guid TEXT, mid INTEGER, "
        "flds TEXT, tags TEXT)"
    )
    con.execute("INSERT INTO notes VALUES (100, 'G1', 999, '你好\x1fhello', '')")
    con.execute(
        "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER, "
        "due INTEGER, ivl INTEGER, factor INTEGER, lapses INTEGER, queue INTEGER, type INTEGER)"
    )
    # ord=0 = "Pinyin -> Hanzi" (P2H) in this model, not "Hanzi -> Significado"
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0, 2527, 4, 2500, 0, 2, 0)")
    con.execute("CREATE TABLE notetypes (id INTEGER, name TEXT)")
    con.execute("INSERT INTO notetypes VALUES (999, 'Chino - HSK (ES/EN)')")
    con.execute(
        "CREATE TABLE templates ("
        "id INTEGER PRIMARY KEY, ntid INTEGER, ord INTEGER, name TEXT)"
    )
    con.execute("INSERT INTO templates VALUES (1, 999, 0, 'Pinyin -> Hanzi')")
    con.commit()
    con.close()

    output = tmp_path / "cards.csv"
    export_stats.export_card_snapshot(collection, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    # ord=0 with name "Pinyin -> Hanzi" -> P2H
    # Old positional mapping would have returned H2M
    assert rows[0]["card_type"] == "P2H"


def test_export_legacy_schema_falls_back_to_positional_ord(tmp_path):
    """When templates/notetypes tables are missing (very old Anki), fall back
    to positional CARD_TYPE_BY_ORD mapping (same behavior as before)."""
    collection = tmp_path / "collection.anki2"
    con = sqlite3.connect(collection)
    con.execute("CREATE TABLE col (decks TEXT)")
    decks_json = json.dumps({"1": {"name": "Legacy Deck"}})
    con.execute("INSERT INTO col (decks) VALUES (?)", (decks_json,))
    # notes without mid column (very old schema)
    con.execute("CREATE TABLE notes (id INTEGER, flds TEXT, tags TEXT, guid TEXT)")
    con.execute("INSERT INTO notes VALUES (100, '你好\x1fhello', '', '')")
    con.execute("CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER)")
    con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 3)")
    con.execute(
        "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
        "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
    )
    con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 1)")
    # No templates or notetypes table at all
    con.commit()
    con.close()

    output = tmp_path / "out.csv"
    export_stats.export_reviews(collection, output)

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    # Falls back to CARD_TYPE_BY_ORD[3] == "PM2H"
    assert rows[0]["card_type"] == "PM2H"


def test_card_name_to_code_mapping_completeness():
    """Verify CARD_NAME_TO_CODE covers all standard template names."""
    expected_codes = {"H2M", "M2H", "H2P", "PM2H", "P2M", "M2P", "P2H", "HM2P", "HP2M", "Toda la información"}
    assert set(export_stats.CARD_NAME_TO_CODE.values()) == expected_codes


def test_export_all_hsk_decks_stable_name_based(tmp_path):
    """Verify name-based lookup works identically for HSK1 through HSK4
    regardless of collection or profile differences."""
    for level in ("HSK1", "HSK2", "HSK3", "HSK4"):
        collection = tmp_path / f"collection_{level}.anki2"
        con = sqlite3.connect(collection)
        con.execute("CREATE TABLE col (id INTEGER, crt INTEGER)")
        con.execute("INSERT INTO col VALUES (1, 1577836800)")
        con.execute("CREATE TABLE decks (id INTEGER, name TEXT)")
        con.execute("INSERT INTO decks VALUES (1, ?)", (f"Chino - {level} (3.0, 2026)",))
        con.execute(
            "CREATE TABLE notes (id INTEGER, guid TEXT, mid INTEGER, "
            "flds TEXT, tags TEXT)"
        )
        con.execute("INSERT INTO notes VALUES (100, 'G1', 999, '测试\x1ftest', ?)", (level,))
        con.execute(
            "CREATE TABLE cards (id INTEGER, nid INTEGER, did INTEGER, odid INTEGER, ord INTEGER)"
        )
        con.execute("INSERT INTO cards VALUES (200, 100, 1, 0, 0)")
        con.execute(
            "CREATE TABLE revlog (id INTEGER, cid INTEGER, ease INTEGER, ivl INTEGER, "
            "lastIvl INTEGER, factor INTEGER, time INTEGER, type INTEGER)"
        )
        con.execute("INSERT INTO revlog VALUES (1735689600000, 200, 3, 4, 1, 2500, 5000, 1)")

        # Same templates table for all levels
        con.execute(
            "CREATE TABLE templates ("
            "id INTEGER PRIMARY KEY, ntid INTEGER, ord INTEGER, name TEXT)"
        )
        con.execute("INSERT INTO templates VALUES (1, 999, 0, 'Hanzi -> Significado')")
        con.commit()
        con.close()

        output = tmp_path / f"out_{level}.csv"
        export_stats.export_reviews(collection, output)

        rows = list(csv.DictReader(output.open(encoding="utf-8")))
        assert len(rows) == 1
        # All levels must resolve ord=0 "Hanzi -> Significado" -> H2M
        assert rows[0]["card_type"] == "H2M", f"{level} failed"


# --- Robustness: empty append target, header order, invalid input, CLI ---


def test_append_to_empty_file_does_full_export(tmp_path):
    """An empty CSV (e.g. left by an interrupted export) is treated as missing."""
    collection = tmp_path / "collection.anki2"
    _make_modern_collection(collection)
    output = tmp_path / "reviews.csv"
    output.touch()

    count = export_stats.export_reviews(collection, output, append=True)

    assert count == 1
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["review_id"] == "1735689600000"


def test_append_header_with_same_columns_in_other_order(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_modern_collection(collection)
    output = tmp_path / "reviews.csv"
    export_stats.export_reviews(collection, output)
    header = output.read_text(encoding="utf-8").splitlines()[0].split(",")
    output.write_text(",".join(reversed(header)) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit, match=r"\(column order differs\)"):
        export_stats.export_reviews(collection, output, append=True)


def test_append_header_mismatch_message_lists_columns(tmp_path):
    collection = tmp_path / "collection.anki2"
    _make_modern_collection(collection)
    output = tmp_path / "reviews.csv"
    output.write_text("review_id,old_column\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        export_stats.export_reviews(collection, output, append=True)

    message = str(exc.value)
    assert "format (missing=[" in message  # no stray space after "("
    assert "extra=[old_column]" in message


def test_front_fields_skips_comments_scripts_and_duplicates():
    qfmt = (
        "{{type:Pinyin}}<div>{{Simplified}}</div>{{Simplified}}"
        "<!-- <a href='plecoapi://?q={{Synonyms}}'> -->"
        "<script>var data = '{{Meaning}}';</script>"
        "{{#Pinyin}}{{Pinyin}}{{/Pinyin}}"
    )
    assert export_stats._front_fields(qfmt) == "type:Pinyin, Simplified, Pinyin"


def test_front_fields_truncates_long_lists():
    qfmt = "".join(f"{{{{Field{i}}}}}" for i in range(30))
    text = export_stats._front_fields(qfmt)
    assert len(text) == 60
    assert text.endswith("...")


def test_front_fields_without_fields():
    assert export_stats._front_fields("<div>static</div>") == "-"


def _run_main(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["zhongwen-anki-export-stats", *map(str, args)])
    export_stats.main()


def test_list_templates_works_on_colpkg(tmp_path, monkeypatch, capsys):
    """--list-templates must extract the .colpkg before opening it."""
    inner = tmp_path / "inner.anki2"
    _make_modern_collection(inner)
    colpkg = tmp_path / "collection.colpkg"
    with zipfile.ZipFile(colpkg, "w") as zf:
        zf.write(inner, "collection.anki21")
    output = tmp_path / "reviews.csv"

    _run_main(monkeypatch, "--collection", colpkg, "--list-templates", "-o", output)

    assert "notetype" in capsys.readouterr().out
    assert not output.exists()  # diagnostic only: nothing is exported


@pytest.mark.parametrize("content", [b"not a database at all", b""])
def test_main_rejects_file_that_is_not_sqlite(tmp_path, monkeypatch, content):
    bogus = tmp_path / "notes.anki2"
    bogus.write_bytes(content)
    with pytest.raises(SystemExit, match="is not a valid Anki collection"):
        _run_main(monkeypatch, "--collection", bogus, "-o", tmp_path / "out.csv")


def test_main_rejects_sqlite_without_revlog(tmp_path, monkeypatch):
    other = tmp_path / "other.db"
    con = sqlite3.connect(other)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.commit()
    con.close()
    with pytest.raises(SystemExit, match="is not a valid Anki collection"):
        _run_main(monkeypatch, "--collection", other, "-o", tmp_path / "out.csv")
