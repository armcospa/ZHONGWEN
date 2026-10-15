"""Export Anki's review history (revlog) to CSV for external analysis.

Reads directly from the local collection.anki2 SQLite file (opened read-only,
so it's safe even while Anki is running) and writes one row per review, joined
with the deck name and the note's first field (the Chinese word).

Supports ``.colpkg`` files (Anki's export format) by opening them as ZIP
archives and decompressing the embedded collection using ``zstandard``.

Supports collecting data from AnkiDroid via sync or export (see
*AnkiDroid Sync* below).

Usage:
    python -m zhongwen_anki.export_stats
    python -m zhongwen_anki.export_stats --deck "HSK1" -o docs/local/estadisticas/anki_reviews.csv
    python -m zhongwen_anki.export_stats --collection "C:\\path\\to\\collection.anki2"
    python -m zhongwen_anki.export_stats --collection "C:\\path\\to\\collection.colpkg"
    python -m zhongwen_anki.export_stats --since 2026-08-01  # incremental export
    python -m zhongwen_anki.export_stats --card-snapshot      # also export card state
    python -m zhongwen_anki.export_stats --vocab-dir data      # enrich with TSV data

AnkiDroid Sync:
    Most users study on AnkiDroid (Android, package com.ichi2.anki).
    There are two ways to get the collection file:

    1. **Cloud sync (recommended):**
       Tap the sync icon in AnkiDroid to push reviews to AnkiWeb, then
       sync Anki Desktop to pull them into the local collection.anki2.
       Run this export tool against that file.

    2. **Export .colpkg from AnkiDroid:**
       AnkiDroid → Study tab → Hamburger menu → Manage → Export
       → Export Bundle (``.colpkg``). Transfer the file to your computer
       and pass ``--collection <path.colpkg>`` to this tool.

Notes on the Anki schema (kept raw on purpose, for faithful downstream analysis):
    - `interval` / `last_interval`: positive = days, negative = seconds
      (Anki uses seconds for the short intervals during learning steps).
    - `ease_factor_percent`: 250 means the interval multiplies by 2.5 on a
      correct review.  Empty for new cards or when factor is 0.
    - `is_correct` is a simple heuristic: ease >= 2 (i.e. not "Again").
      Empty when ease == 0 or for system actions (type 4/5).
    - `is_user_answer` is True when ease >= 1 AND type NOT IN (4, 5),
      marking reviews that are actual user responses (not system actions
      like reschedule or delete).
    - `tags` reflects the note's tags *right now* (e.g. "leech", "HSK1"), not
      at the time of that historical review -- Anki doesn't keep a per-review
      snapshot of tags, so a tag added/removed later shows up on every row.
    - `current_filtered_deck` is populated only if the card is *still*
      sitting inside a filtered deck at export time; once a filtered deck is
      emptied there is no way to recover which one a past review happened
      in -- Anki's revlog does not record deck membership per review, only
      `review_type == "cram/filtered"` (whether it was a cram-type review at
      all). `card_type` (see CARD_TYPE_BY_ORD below) is the durable
      equivalent for "which skill was this": unlike a filtered deck, a
      card's template never changes over its lifetime.
"""
import argparse
import csv
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

EASE_LABELS = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
REVIEW_TYPE_LABELS = {
    0: "learning",
    1: "review",
    2: "relearning",
    3: "cram/filtered",
    4: "manual",
    5: "rescheduled",
}

# cards.ord -> card type code.  Used as fallback when the collection has
# no usable templates table (legacy schema, or note type not found).
# Must be kept in sync with build_deck.TEMPLATES order.
CARD_TYPE_BY_ORD = {
    0: "H2M",
    1: "M2H",
    2: "H2P",
    3: "PM2H",
    4: "P2M",
    5: "M2P",
    6: "P2H",
    7: "HM2P",
    8: "HP2M",
    9: "Toda la información",
}

# (notetype name, template name) -> code. Takes precedence over
# CARD_NAME_TO_CODE for legacy models whose template names don't describe
# what the template actually asks (verified against each template's front side).
TEMPLATE_OVERRIDES: dict[tuple[str, str], str] = {
    ("Chino - HSK (ES/EN)+", "Pinyin -> Significado"): "M2P",
}


# Template display name (as stored in Anki's templates table) -> card type code.
# This is the primary, name-based lookup that works regardless of template
# position (ord) in the model, making it stable across deck variants
# with different template orders (e.g. "Chino - HSK (ES/EN)+" with 11 templates).
CARD_NAME_TO_CODE = {
    # Descriptive names used by earlier versions of the deck
    "Hanzi -> Significado": "H2M",
    "Significado -> Hanzi": "M2H",
    "Hanzi -> Pinyin": "H2P",
    "Pinyin + Significado -> Hanzi": "PM2H",
    "Pinyin -> Significado": "P2M",
    "Significado -> Pinyin": "M2P",
    "Pinyin -> Hanzi": "P2H",
    "Hanzi + Significado -> Pinyin": "HM2P",
    "Hanzi + Pinyin -> Significado": "HP2M",
    # Codes used as template names in some collection variants (self-mapping)
    "H2M": "H2M",
    "M2H": "M2H",
    "H2P": "H2P",
    "PM2H": "PM2H",
    "P2M": "P2M",
    "M2P": "M2P",
    "P2H": "P2H",
    "HM2P": "HM2P",
    "HP2M": "HP2M",
    # + variant / legacy collection names
    "Escribir Pinyin": "H2P",
    "Escribir Hanzi": "PM2H",
    "PS2H": "PM2H",
    "P2S": "P2M",
    "HS2P": "HM2P",
    "HP2S": "HP2M",
    "S2P": "M2P",
    # Info / All-information card (canonical name maps to itself)
    "Toda la información": "Toda la información",
    "Todas las tarjetas": "Toda la información",
    "All Information": "Toda la información",
}

# Card snapshot queue labels
QUEUE_LABELS = {
    -3: "buried/user",
    -2: "buried/scheduler",
    -1: "suspended",
    0: "new",
    1: "learning",
    2: "review",
    3: "relearning",
    4: "preview",
}

# Card snapshot type labels
TYPE_LABELS = {0: "new", 1: "learning", 2: "review", 3: "relearning"}


# --- Collection discovery ------------------------------------------------


def _default_collection_candidates():
    """Find Anki collection files on this system.

    Searches:
      - Windows: %APPDATA%\\Anki2\\*/collection.anki2
      - macOS: ~/Library/Application Support/Anki2/*/collection.anki2
      - Linux: ~/.local/share/Anki2/*/collection.anki2
      - AnkiDroid backup: collection.anki2 / collection.colpkg in current directory
    """
    candidates = []

    # Standard Anki Desktop locations
    search_paths = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        search_paths.append(Path(appdata) / "Anki2")
    home = Path.home()
    search_paths.append(home / "Library" / "Application Support" / "Anki2")
    search_paths.append(home / ".local" / "share" / "Anki2")

    for base in search_paths:
        if base.exists():
            candidates.extend(sorted(base.glob("*/collection.anki2")))

    # Fallback: check current directory for AnkiDroid backup/export
    for name in ("collection.anki2", "collection.colpkg"):
        local = Path(name)
        if local.exists() and local not in candidates:
            candidates.append(local)

    return candidates


def _find_collection(explicit: Optional[Path]) -> Path:
    if explicit is not None:
        if not explicit.exists():
            raise SystemExit(f"Collection file not found: {explicit}")
        return explicit

    candidates = _default_collection_candidates()
    if not candidates:
        raise SystemExit(
            "Could not auto-detect an Anki collection.\n"
            "Options:\n"
            "  1. Sync AnkiDroid → AnkiWeb → Anki Desktop, then re-run.\n"
            "  2. Export a .colpkg bundle from AnkiDroid and pass --collection <path>.\n"
            "  3. Pass --collection <path to collection.anki2 or .colpkg> explicitly."
        )
    if len(candidates) > 1:
        listing = "\n".join(f"  - {c}" for c in candidates)
        raise SystemExit(
            "Multiple Anki profiles found; pass --collection to pick one:\n" + listing
        )
    return candidates[0]


# --- .colpkg / collection extraction ------------------------------------


def _extract_colpkg_to_sqlite(collection_path: Path) -> Path:
    """Extract the SQLite collection from a .colpkg archive.

    Returns the path to the extracted (and decompressed if needed) .anki2 file.
    For anki21b collections, performs zstandard streaming decompression.

    Priority order: collection.anki21b > collection.anki21 > collection.anki2
    (Falls back to unprefixed names for legacy compatibility.)
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="anki_colpkg_"))
    try:
        with zipfile.ZipFile(collection_path, "r") as zf:
            files = zf.namelist()

        # Determine which collection file to use.
        # Modern Anki uses "collection." prefix; fall back to bare names.
        preferred_candidates = (
            "collection.anki21b", "collection.anki21", "collection.anki2",
            "anki21b", "anki21", "anki2",
        )
        chosen_file = None
        for candidate in preferred_candidates:
            if candidate in files:
                chosen_file = candidate
                break

        if chosen_file is None:
            raise SystemExit(
                f"No collection file found in .colpkg archive. "
                f"Expected one of: collection.anki21b, collection.anki21, collection.anki2. "
                f"Found: {files}"
            )

        is_legacy_anki2_only = (
            chosen_file in ("collection.anki2", "anki2")
            and not any(c in files for c in ("collection.anki21b", "collection.anki21", "anki21b", "anki21"))
        )

        output_path = tmp_dir / "collection.anki2"

        is_anki21b = chosen_file.endswith("anki21b")

        if is_anki21b:
            # Decompress using zstandard streaming directly from ZIP stream
            try:
                import zstandard as zstd
            except ImportError:
                raise SystemExit(
                    "zstandard package is required to open .colpkg files with anki21b collections. "
                    "Install it with: pip install zstandard"
                )
            with zipfile.ZipFile(collection_path, "r") as zf, zf.open(chosen_file) as src, \
                 zstd.ZstdDecompressor().stream_reader(src) as reader, \
                 output_path.open("wb") as out:
                shutil.copyfileobj(reader, out)
        else:
            # anki21 or anki2 are already uncompressed SQLite — stream, don't buffer
            with zipfile.ZipFile(collection_path, "r") as zf, zf.open(chosen_file) as src, \
                 output_path.open("wb") as out:
                shutil.copyfileobj(src, out)

        # Detect dummy-only collection: if legacy-only and revlog is empty, error out
        if is_legacy_anki2_only:
            check_con = sqlite3.connect(f"file:{output_path.as_posix()}?mode=ro", uri=True)
            try:
                count = check_con.execute("SELECT COUNT(*) FROM revlog").fetchone()[0]
            except sqlite3.OperationalError:
                count = 0
            finally:
                check_con.close()
            if count == 0:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                raise SystemExit(
                    "The .colpkg only contains the empty legacy-compatibility collection. "
                    "Re-export it from Anki/AnkiDroid without checking "
                    "'include legacy-compatibility collection'."
                )

        return output_path
    except Exception:
        # Clean up temp directory on failure
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


# --- Vocab enrichment ----------------------------------------------------


def _load_vocab_data(vocab_dir: Path) -> dict:
    """Load all input.tsv files and index by GUID.

    Returns a dict mapping GUID -> {pinyin, meaning, meaning_es, level, ...}.

    Note: If the same GUID appears in multiple TSV files (e.g., a word that
    exists in both HSK1 and HSK2), the last file processed wins. Files are
    processed in sorted order, so higher levels override lower ones.
    """
    vocab = {}
    for tsv in sorted(vocab_dir.glob("*/input.tsv")):
        level = tsv.parent.name.upper()
        try:
            df = pd.read_csv(tsv, sep="\t", dtype=str).fillna("")
        except Exception as e:
            logger.error("Failed to load vocab file %s: %s", tsv, e)
            continue
        for _, row in df.iterrows():
            guid = row.get("Guid", "").strip()
            if not guid:
                continue
            vocab[guid] = {
                "pinyin": row.get("Pinyin", ""),
                "meaning": row.get("Meaning", ""),
                "meaning_es": row.get("MeaningES", ""),
                "level": level,
                "traditional": row.get("Traditional", ""),
                "sentence": row.get("SentenceSimplified", ""),
                "sentence_meaning": row.get("SentenceMeaning", ""),
                "synonyms": row.get("Synonyms", ""),
            }
    return vocab

# --- Template lookup helpers ---------------------------------------------


def _load_template_map(con) -> dict:
    """Load {ntid: {"name": str, "templates": {ord: template_name}}} from the collection.

    Modern Anki (2.1.20+) stores templates in a dedicated ``templates`` table
    and note type names in the ``notetypes`` table.  Both tables use a
    ``unicase`` collation (Anki's own Turkish/diacritics-aware comparison)
    which must be registered before querying; we register a simple byte-order
    fallback.

    Returns an empty dict when the ``templates`` table is not available.
    Note: Collections prior to Anki 2.1.28 (where templates lived in
    col.models JSON blobs) are not supported by name and will fall back
    to positional ord mapping.
    """
    template_map = {}

    # --- Try modern `templates` table ---------------------------------------
    try:
        # Register a fallback for "unicase" (Anki's Turkish/diacritics-aware
        # collation).  We open read-only so Anki's own registration isn't
        # available; a simple byte-order comparison is sufficient.
        con.create_collation("unicase", lambda a, b: (a > b) - (a < b))

        # Load notetype names
        notetype_names: dict[int, str] = {}
        for row in con.execute("SELECT id, name FROM notetypes").fetchall():
            if isinstance(row, dict) or hasattr(row, "keys"):
                notetype_names[row["id"]] = row["name"]
            else:
                notetype_names[row[0]] = row[1]

        # Load templates
        rows = con.execute("SELECT ntid, ord, name FROM templates").fetchall()
        for row in rows:
            if isinstance(row, dict) or hasattr(row, "keys"):
                ntid, ord_, name = row["ntid"], row["ord"], row["name"]
            else:
                ntid, ord_, name = row
            template_map.setdefault(ntid, {"name": notetype_names.get(ntid, "")})
            template_map[ntid].setdefault("templates", {})[ord_] = name
    except (sqlite3.OperationalError, sqlite3.ProgrammingError):
        pass

    return template_map


def _resolve_card_type(card_ord: int, note_ntid, template_map: dict) -> tuple:
    """Resolve card type code, template name, and notetype name for a card.

    Priority order:
    1. ``TEMPLATE_OVERRIDES[(notetype_name, template_name)]``
    2. ``CARD_NAME_TO_CODE[template_name]``
    3. The template name itself (when known but not mapped)
    4. Positional ``CARD_TYPE_BY_ORD`` (only when template info is unavailable)

    Args:
        card_ord: The ``cards.ord`` value (0-based template index).
        note_ntid: The ``notes.mid`` (note type / model id) for this card's note.
        template_map: Output of ``_load_template_map(con)``.

    Returns:
        ``(card_type_code, template_name, notetype_name)`` — the code for the
        ``card_type`` column, the raw template name (or ``""``) for the
        ``template_name`` column, and the notetype/model name (or ``""``) for
        the ``notetype`` column.
    """
    nt_map = template_map.get(note_ntid)
    if nt_map is not None:
        notetype_name = nt_map.get("name", "")
        templates = nt_map.get("templates", {})
        template_name = templates.get(card_ord)
        if template_name:
            # 1. Check overrides first
            override_code = TEMPLATE_OVERRIDES.get((notetype_name, template_name))
            if override_code:
                return override_code, template_name, notetype_name
            # 2. Check CARD_NAME_TO_CODE
            code = CARD_NAME_TO_CODE.get(template_name)
            if code:
                return code, template_name, notetype_name
            # 3. Return template name itself
            return template_name, template_name, notetype_name
    # 4. Fallback: positional ord mapping (legacy collections / missing template map)
    code = CARD_TYPE_BY_ORD.get(card_ord, f"(ord {card_ord})")
    return code, "", ""


# --- Deck / schema helpers -----------------------------------------------



def _load_decks(con) -> dict:
    """Return {deck_id: deck_name}, supporting both modern and legacy schema."""
    try:
        return {row["id"]: row["name"] for row in con.execute("SELECT id, name FROM decks")}
    except sqlite3.OperationalError:
        decks_raw = con.execute("SELECT decks FROM col").fetchone()["decks"]
        return {int(k): v["name"] for k, v in json.loads(decks_raw).items()}


def _get_col_crt(con) -> float:
    """Get collection creation timestamp (seconds since epoch).

    col.crt is stored as epoch seconds in modern Anki. Falls back to 0 for legacy.
    """
    try:
        row = con.execute("SELECT crt FROM col").fetchone()
        if row and row["crt"]:
            return float(row["crt"])
    except sqlite3.OperationalError:
        pass
    return 0.0


def _get_config_int(con, key: str) -> Optional[int]:
    """Read an integer value from Anki's config table (one row per key; val is a JSON blob)."""
    try:
        row = con.execute("SELECT val FROM config WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None or row[0] is None:
        return None
    try:
        return int(json.loads(row[0]))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _get_rollover_hour(con) -> int:
    """Read the day-rollover hour from the Anki config (default 4).

    Modern Anki stores one row per key in the ``config`` table, so the
    rollover hour lives in ``key='rollover'`` with ``val='4'`` (a JSON
    blob). Falls back to 4 when the key is absent or unreadable.
    """
    v = _get_config_int(con, "rollover")
    return 4 if v is None else v


# --- Date helpers --------------------------------------------------------


def _calculate_due_date(
    due: int, queue: int, card_type: int, odue: int,
    col_crt: float, is_filtered: bool, rollover_hour: int = 4,
    creation_offset_min: Optional[int] = None,
) -> str:
    """Calculate the due date for a card based on its queue and due field.

    Semantics of ``cards.due`` depend on the queue/card_type:

    - queue 0 (new): position in the new queue — not a date.
    - queue 1 (learning) / queue 4 (preview): **epoch seconds** (absolute),
      converted in local time.
    - queue 2 (review) / queue 3 (relearning-day): **day number** from
      collection creation (offset by ``rollover_hour``). Anki (scheduler v3)
      counts this day number in the collection's *creation* timezone
      (``creationOffset``, minutes west of UTC), so day 0 is computed in
      that timezone, not in local time.
    - queue -1 (suspended): no due date.
    - queue -2/-3 (buried): inherit from underlying queue.

    For filtered-deck cards (``odid != 0``), the real due is in ``odue``
    with the same semantics; ``due`` is ``-100000 + position`` and carries
    no date meaning.

    Args:
        due: The raw due field from the cards table.
        queue: Queue value.
        card_type: Card type (0=new, 1=learning, 2=review, 3=relearning).
        odue: Original due date for filtered deck cards (same semantics as due).
        col_crt: Collection creation timestamp in **seconds**.
        is_filtered: Whether the card is in a filtered deck (odid != 0).
        rollover_hour: Anki's day-rollover hour (default 4 AM).
        creation_offset_min: The collection's ``creationOffset`` (minutes
            west of UTC).  When given, day 0 is computed in that timezone;
            when absent (old collections), local time is used as fallback.

    Returns:
        Date string in YYYY-MM-DD format, or empty string if not applicable.
    """
    if queue == -1 or queue == 0:
        # Suspended / new cards have no due date.
        return ""

    # For filtered-deck cards, use odue when available.
    if is_filtered and odue:
        raw = odue
    elif is_filtered:
        # Filtered card without odue — due is -100000+position, not a date.
        return ""
    else:
        raw = due

    # Buried cards: treat like their underlying type (use card_type).
    if raw > 1_000_000_000:
        # Epoch seconds (learning/preview queues, or cards buried in learning).
        return datetime.fromtimestamp(raw).strftime("%Y-%m-%d")

    if card_type in (2, 3) or queue in (2, 3, -2, -3):
        # Day number from collection creation, offset by rollover.
        if col_crt > 0:
            if creation_offset_min is not None:
                tz = timezone(timedelta(minutes=-creation_offset_min))
                day0 = (datetime.fromtimestamp(col_crt, tz) - timedelta(hours=rollover_hour)).date()
            else:
                # Old collections without creationOffset: crt already marks the
                # start of the local day.
                day0 = (datetime.fromtimestamp(col_crt) - timedelta(hours=rollover_hour)).date()
            return (day0 + timedelta(days=raw)).strftime("%Y-%m-%d")

    return ""


# --- Export functions ----------------------------------------------------


def _build_review_row(
    row, decks, vocab, deck_filter=None, template_map=None, note_ntid=None
):
    """Build a CSV row values list from a revlog row.

    Returns the list of values (without writing) or None when the row
    should be skipped (deck filter mismatch).

    Args:
        row: Database row from the revlog query.
        decks: {deck_id: deck_name} mapping.
        vocab: Optional vocab enrichment dict keyed by note GUID.
        deck_filter: Optional deck name filter (substring match).
        template_map: Optional {ntid: {ord: template_name}} from _load_template_map.
        note_ntid: The notes.mid (note type id) for this card's note.
    """
    home_deck_id = row["orig_deck_id"] or row["deck_id"]
    deck_name = decks.get(home_deck_id, "")
    if deck_filter and deck_filter.lower() not in deck_name.lower():
        return None
    filtered_deck_name = decks.get(row["deck_id"], "") if row["orig_deck_id"] else ""
    word = row["flds"].split("\x1f")[0]
    card_type, template_name, notetype = _resolve_card_type(
        row["card_ord"], note_ntid, template_map or {}
    )
    tags = row["tags"].strip()
    note_guid = row["note_guid"] if row["note_guid"] else ""

    ease = row["ease"]
    review_type = row["review_type"]
    factor = row["factor"]

    # is_user_answer: True when ease >= 1 AND type NOT IN (4, 5)
    is_user_answer = ease >= 1 and review_type not in (4, 5)

    # is_correct: empty when ease == 0 OR type IN (4, 5), else based on ease >= 2
    if ease == 0 or review_type in (4, 5):
        is_correct = ""
    else:
        is_correct = int(ease >= 2)

    # ease_factor_percent: empty for new cards (factor == 0) or factor missing
    if factor:
        ease_factor_percent = round(factor / 10, 1)
    else:
        ease_factor_percent = ""

    base_values = [
        row["review_epoch_ms"],
        datetime.fromtimestamp(row["review_epoch_ms"] / 1000).isoformat(sep=" ", timespec="seconds"),
        deck_name,
        filtered_deck_name,
        row["note_id"],
        row["card_id"],
        word,
        card_type,
        notetype,
        template_name,
        tags,
        note_guid,
        ease,
        EASE_LABELS.get(ease, ease),
        is_user_answer,
        is_correct,
        row["interval"],
        row["last_interval"],
        ease_factor_percent,
        round(row["time_ms"] / 1000, 1),
        REVIEW_TYPE_LABELS.get(review_type, review_type),
    ]

    if vocab:
        v = vocab.get(note_guid, {})
        base_values.extend([
            v.get("pinyin", ""),
            v.get("meaning", ""),
            v.get("meaning_es", ""),
            v.get("level", ""),
            v.get("traditional", ""),
            v.get("sentence", ""),
            v.get("sentence_meaning", ""),
            v.get("synonyms", ""),
        ])

    return base_values


def export_reviews(
    collection_path: Path,
    output_path: Path,
    deck_filter: Optional[str] = None,
    since: Optional[str] = None,
    vocab_dir: Optional[Path] = None,
    append: bool = False,
) -> int:
    """Export review history (revlog) to CSV.

    Args:
        collection_path: Path to collection.anki2 or collection.colpkg.
        output_path: Destination CSV file.
        deck_filter: Only include decks whose name contains this text.
        since: Only include reviews on or after this date ("YYYY-MM-DD", local time).
        vocab_dir: If provided, enrich rows with TSV vocab data (by GUID).
        append: If True and output exists, append only new reviews (by review_id).

    Returns:
        Number of review rows written.
    """
    uri = f"file:{collection_path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row

    decks = _load_decks(con)
    template_map = _load_template_map(con)

    # Check if notes table has `mid` column (modern Anki 2.1+)
    note_columns = {
        row["name"]
        for row in con.execute("PRAGMA table_info(notes)").fetchall()
    }
    has_note_mid = "mid" in note_columns

    # Load vocab enrichment data if requested
    vocab = {}
    if vocab_dir is not None and vocab_dir.exists():
        vocab = _load_vocab_data(vocab_dir)

    # Build WHERE clause for deck filter and --since
    where_clauses = []
    params = {}
    if since:
        since_dt = datetime.strptime(since, "%Y-%m-%d")
        since_ms = int(since_dt.timestamp() * 1000)
        where_clauses.append("revlog.id >= :since_ms")
        params["since_ms"] = since_ms

    note_ntid_select = "notes.mid AS note_ntid" if has_note_mid else "0 AS note_ntid"
    query = f"""
        SELECT revlog.id AS review_epoch_ms, revlog.cid AS card_id, revlog.ease,
                revlog.ivl AS interval, revlog.lastIvl AS last_interval,
                revlog.factor AS factor, revlog.time AS time_ms, revlog.type AS review_type,
                cards.did AS deck_id, cards.odid AS orig_deck_id, cards.nid AS note_id,
                cards.ord AS card_ord, notes.flds AS flds, notes.tags AS tags,
                notes.guid AS note_guid, {note_ntid_select}
        FROM revlog
        JOIN cards ON cards.id = revlog.cid
        JOIN notes ON notes.id = cards.nid
    """
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    query += " ORDER BY revlog.id"

    rows = con.execute(query, params).fetchall()

    # Determine columns based on vocab enrichment
    base_columns = [
        "review_id", "review_datetime", "deck", "current_filtered_deck", "note_id", "card_id",
        "word", "card_type", "notetype", "template_name", "tags", "note_guid",
        "ease", "ease_label", "is_user_answer", "is_correct",
        "interval", "last_interval", "ease_factor_percent",
        "time_seconds", "review_type",
    ]
    vocab_columns = [
        "pinyin", "meaning", "meaning_es", "vocab_level", "traditional",
        "sentence", "sentence_meaning", "synonyms",
    ]
    all_columns = base_columns + (vocab_columns if vocab else [])

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # --- append mode -------------------------------------------------------
    # An empty file (e.g. left by an interrupted export) has no header to
    # check against, so it is treated like a missing one: full export below.
    if append and output_path.exists() and output_path.stat().st_size > 0:
        existing_ids = set()
        with output_path.open("r", newline="", encoding="utf-8") as check_f:
            reader = csv.reader(check_f)
            header = next(reader, [])
            if header != all_columns:
                existing_set = set(header)
                new_set = set(all_columns)
                missing = [c for c in all_columns if c not in existing_set]
                extra = [c for c in header if c not in new_set]
                parts = []
                if missing:
                    parts.append(f"missing=[{', '.join(missing)}]")
                if extra:
                    parts.append(f"extra=[{', '.join(extra)}]")
                detail = " ".join(parts) or "column order differs"
                raise SystemExit(
                    f"The header of {output_path} does not match the current export format"
                    f" ({detail}).\n"
                    f"Repeat your original export command (without --append) to regenerate it.\n"
                    f"Make sure to use the same options (e.g. --vocab-dir) as the original export."
                )
            for r in reader:
                if r:
                    existing_ids.add(r[0])  # review_id is column 0
        appended = 0
        already_present = 0
        filtered_out = 0
        with output_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in rows:
                review_id = str(row["review_epoch_ms"])
                if review_id in existing_ids:
                    already_present += 1
                    continue
                values = _build_review_row(
                    row, decks, vocab, deck_filter,
                    template_map=template_map, note_ntid=row["note_ntid"],
                )
                if values is None:
                    filtered_out += 1
                    continue
                writer.writerow(values)
                appended += 1
        print(
            f"Appended {appended} new reviews "
            f"({already_present} already present, {filtered_out} filtered out)"
        )
        con.close()
        return appended
    # -----------------------------------------------------------------------

    written = 0
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(all_columns)
        for row in rows:
            values = _build_review_row(
                row, decks, vocab, deck_filter,
                template_map=template_map, note_ntid=row["note_ntid"],
            )
            if values is None:
                continue
            writer.writerow(values)
            written += 1

    con.close()
    label = f"since {since}" if since else "total"
    print(f"Wrote {written:,} reviews ({label}) -> {output_path}")
    return written


def export_card_snapshot(
    collection_path: Path,
    output_path: Path,
    deck_filter: Optional[str] = None,
) -> int:
    """Export current state of all cards to CSV.

    Captures a snapshot of scheduling state: interval, ease factor, lapses,
    queue status, due date, FSRS metrics, etc. Useful for understanding where
    each card stands at export time.

    Args:
        collection_path: Path to collection.anki2 or collection.colpkg.
        output_path: Destination CSV file.
        deck_filter: Only include decks whose name contains this text.

    Returns:
        Number of card rows written.
    """
    uri = f"file:{collection_path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row

    decks = _load_decks(con)
    template_map = _load_template_map(con)
    col_crt = _get_col_crt(con)
    rollover = _get_rollover_hour(con)
    creation_offset = _get_config_int(con, "creationOffset")

    # Determine which columns exist in the cards table (older Anki versions
    # may lack odue, reps, data columns)
    card_columns = {
        row["name"]
        for row in con.execute("PRAGMA table_info(cards)").fetchall()
    }
    has_odue = "odue" in card_columns
    has_reps = "reps" in card_columns
    has_data = "data" in card_columns

    # Check if notes table has `mid` column (modern Anki 2.1+)
    note_columns = {
        row["name"]
        for row in con.execute("PRAGMA table_info(notes)").fetchall()
    }
    has_note_mid = "mid" in note_columns

    extra_select = "cards.due"
    if has_odue:
        extra_select += ", cards.odue"
    else:
        extra_select += ", 0 AS odue"
    extra_select += ", cards.ivl, cards.factor, cards.lapses, cards.queue, cards.type"
    if has_reps:
        extra_select += ", cards.reps"
    else:
        extra_select += ", 0 AS reps"
    if has_data:
        extra_select += ", cards.data"
    else:
        extra_select += ", '' AS data"

    note_ntid_select = "notes.mid AS note_ntid" if has_note_mid else "0 AS note_ntid"
    query = f"""
        SELECT cards.id AS card_id, cards.nid AS note_id,
               cards.did AS deck_id, cards.odid AS orig_deck_id,
               cards.ord AS card_ord,
               {extra_select},
               notes.flds AS flds, notes.tags AS tags,
               notes.guid AS note_guid, {note_ntid_select}
        FROM cards
        JOIN notes ON notes.id = cards.nid
    """
    rows = con.execute(query).fetchall()

    columns = [
        "card_id", "note_id", "note_guid", "deck", "orig_deck",
        "word", "card_type", "notetype", "template_name", "tags",
        "queue", "queue_label", "type", "type_label",
        "due", "due_date", "interval", "ease_factor_percent", "lapses",
        "reps", "fsrs_stability", "fsrs_difficulty",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            home_deck_id = row["orig_deck_id"] or row["deck_id"]
            deck_name = decks.get(home_deck_id, "")
            if deck_filter and deck_filter.lower() not in deck_name.lower():
                continue
            orig_deck_name = decks.get(row["orig_deck_id"], "") if row["orig_deck_id"] else ""
            word = row["flds"].split("\x1f")[0]
            card_type_name, notetype, template_name = _resolve_card_type(
                row["card_ord"], row["note_ntid"], template_map
            )
            tags = row["tags"].strip()
            note_guid = row["note_guid"] if row["note_guid"] else ""
            queue = row["queue"]
            ctype = row["type"]
            factor = row["factor"]
            is_filtered = bool(row["orig_deck_id"])

            # Parse FSRS data from cards.data JSON field
            fsrs_stability = ""
            fsrs_difficulty = ""
            raw_data = row["data"]
            if raw_data:
                try:
                    data_obj = json.loads(raw_data)
                    if isinstance(data_obj, dict):
                        fsrs_stability = data_obj.get("s", "")
                        fsrs_difficulty = data_obj.get("d", "")
                except (json.JSONDecodeError, TypeError):
                    pass

            # due_date calculation
            due_date = _calculate_due_date(
                due=row["due"],
                queue=queue,
                card_type=ctype,
                odue=row["odue"] or 0,
                col_crt=col_crt,
                is_filtered=is_filtered,
                rollover_hour=rollover,
                creation_offset_min=creation_offset,
            )

            # ease_factor_percent: empty when factor == 0
            if factor:
                ease_factor_percent = round(factor / 10, 1)
            else:
                ease_factor_percent = ""

            # reps: review count (may be None for very old cards)
            reps = row["reps"] if row["reps"] is not None else 0

            writer.writerow([
                row["card_id"],
                row["note_id"],
                note_guid,
                deck_name,
                orig_deck_name,
                word,
                card_type_name,
                notetype,
                template_name,
                tags,
                queue,
                QUEUE_LABELS.get(queue, queue),
                ctype,
                TYPE_LABELS.get(ctype, ctype),
                row["due"],
                due_date,
                row["ivl"],
                ease_factor_percent,
                row["lapses"],
                reps,
                fsrs_stability,
                fsrs_difficulty,
            ])
            written += 1

    con.close()
    print(f"Wrote {written:,} cards -> {output_path}")
    return written


# --- Backwards-compatible alias ------------------------------------------


def export(collection_path: Path, output_path: Path, deck_filter: Optional[str]) -> None:
    """Backwards-compatible alias for export_reviews()."""
    export_reviews(collection_path, output_path, deck_filter)


# --- CLI -----------------------------------------------------------------


def _validate_since(since_str: str) -> str:
    """Validate and return the --since date string.

    Args:
        since_str: Date string in YYYY-MM-DD format.

    Returns:
        The validated date string.

    Raises:
        argparse.ArgumentTypeError: If the date format is invalid.
    """
    try:
        datetime.strptime(since_str, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date format: '{since_str}'. Expected YYYY-MM-DD (e.g. 2025-01-15)."
        )
    return since_str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Anki review history and card state to CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export all reviews
  zhongwen-anki-export-stats

  # Incremental export since a date
  zhongwen-anki-export-stats --since 2026-08-01

  # Export reviews enriched with vocab data
  zhongwen-anki-export-stats --vocab-dir data

  # Also export current card state snapshot
  zhongwen-anki-export-stats --card-snapshot

  # All exports at once
  zhongwen-anki-export-stats --card-snapshot --vocab-dir data

AnkiDroid users:
  Sync: Tap sync icon in AnkiDroid -> sync in Anki Desktop, then run this tool.
  Export: AnkiDroid deck list -> menu (⋮) -> "Export collection" -> Collection Package (.colpkg),
          then pass --collection <file>.  Anki Desktop backups also work
          (%APPDATA%\\Anki2\\{profile}\\backups\\*.colpkg).
        """,
    )
    parser.add_argument("--collection", type=Path, default=None,
                         help="Path to collection.anki2 or .colpkg (auto-detected if omitted).")
    parser.add_argument("-o", "--output", type=Path,
                         default=Path("docs/local/estadisticas/anki_reviews.csv"),
                         help="Output CSV for reviews (default: docs/local/estadisticas/anki_reviews.csv).")
    parser.add_argument("--deck", type=str, default=None,
                         help="Only include reviews/cards from decks whose name contains this text.")
    parser.add_argument("--since", type=_validate_since, default=None,
                          help='Only export reviews on or after this date (format: YYYY-MM-DD, interpreted in local time).')
    parser.add_argument("--append", action="store_true", default=False,
                          help="Append only new reviews to an existing CSV (requires matching header).")
    parser.add_argument("--vocab-dir", type=Path, default=None,
                         help="Directory with input.tsv files to enrich export with vocab data (e.g. 'data').")
    parser.add_argument("--card-snapshot", action="store_true", default=False,
                         help="Also export current state of all cards (interval, lapses, queue, etc.).")
    parser.add_argument("--card-snapshot-output", type=Path, default=None,
                          help="Output path for card snapshot (default: <output>.cards.csv).")
    parser.add_argument("--list-templates", action="store_true", default=False,
                          help="Print a table of all templates (notetype, ord, code, front fields) and exit.")
    parser.add_argument("--all", action="store_true", dest="show_all_templates", default=False,
                          help="With --list-templates: also show built-in note types (Basic, Cloze…).")
    return parser.parse_args()


def _extract_qfmt(blob: bytes) -> str:
    """Read q_format from templates.config protobuf blob (field 1, tag 0x0A)."""
    if not blob or blob[0] != 0x0A:
        return ""
    length, shift, i = 0, 0, 1
    while True:
        b = blob[i]; i += 1
        length |= (b & 0x7F) << shift
        if not b & 0x80:
            break
        shift += 7
    return blob[i:i + length].decode("utf-8", "replace")


def _front_fields(qfmt: str, max_len: int = 60) -> str:
    """Unique field names {{...}} shown on the front, in order of appearance.

    HTML comments and scripts are skipped (commented-out Pleco links and
    embedded HanziWriter data would otherwise flood the column).
    """
    visible = re.sub(r"<!--.*?-->|<script.*?</script>", "", qfmt, flags=re.S)
    fields = dict.fromkeys(re.findall(r"\{\{([^#^/!}][^}]*)\}\}", visible))
    text = ", ".join(fields) or "-"
    return text if len(text) <= max_len else text[:max_len - 3] + "..."


def _list_templates(collection_path: Path, show_all: bool = False) -> None:
    """Print a diagnostic table of all templates and exit."""
    uri = f"file:{collection_path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row

    template_map = _load_template_map(con)

    # Load config blobs (protobuf) to extract q_format front fields
    config_by_nkid: dict[tuple[int, int], bytes] = {}
    try:
        for row in con.execute("SELECT ntid, ord, config FROM templates").fetchall():
            if isinstance(row, dict) or hasattr(row, "keys"):
                config_by_nkid[(row["ntid"], row["ord"])] = row["config"]
            else:
                config_by_nkid[(row[0], row[1])] = row[2]
    except sqlite3.OperationalError:
        pass

    # Count reviews per (ntid, ord)
    try:
        review_counts = {}
        for row in con.execute("""
            SELECT notes.mid AS ntid, cards.ord, COUNT(*) AS cnt
            FROM revlog
            JOIN cards ON cards.id = revlog.cid
            JOIN notes ON notes.id = cards.nid
            GROUP BY notes.mid, cards.ord
        """).fetchall():
            review_counts[(row["ntid"], row["ord"])] = row["cnt"]
    except sqlite3.OperationalError:
        review_counts = {}

    # Get notetypes with cards (to filter out built-in types)
    try:
        notetypes_with_cards = {
            row["mid"] for row in con.execute("SELECT DISTINCT mid FROM notes").fetchall()
        }
    except sqlite3.OperationalError:
        notetypes_with_cards = set(template_map.keys())

    headers = ["notetype", "ntid", "ord", "template_name", "front_fields", "resolved_code", "n_reviews"]
    rows: list[list[str]] = []
    for ntid in sorted(template_map.keys()):
        nt_info = template_map[ntid]
        notetype_name = nt_info.get("name", "")
        templates = nt_info.get("templates", {})

        if not show_all and ntid not in notetypes_with_cards:
            continue

        for ord_ in sorted(templates.keys()):
            template_name = templates[ord_]
            resolved_code, _, _ = _resolve_card_type(ord_, ntid, template_map)
            # Extract front fields from protobuf config blob
            config_blob = config_by_nkid.get((ntid, ord_), b"")
            qfmt = _extract_qfmt(config_blob)
            front_fields = _front_fields(qfmt)
            n_reviews = review_counts.get((ntid, ord_), 0)
            rows.append([
                notetype_name, str(ntid), str(ord_), template_name,
                front_fields, resolved_code, str(n_reviews),
            ])

    # Print table
    col_widths = [max(len(str(r[i])) for r in [headers] + rows) + 2 for i in range(len(headers))]
    header_line = "".join(str(h).ljust(w) for h, w in zip(headers, col_widths))
    print(header_line)
    print("-" * len(header_line))
    for row in rows:
        print("".join(str(v).ljust(w) for v, w in zip(row, col_widths)))

    con.close()


def _validate_collection(collection_path: Path, shown_path: Path) -> None:
    """Fail with a clear message unless *collection_path* is an Anki collection.

    *shown_path* is the path the user passed (it differs from
    *collection_path* when a .colpkg was extracted to a temp file).
    """
    uri = f"file:{collection_path.as_posix()}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
        try:
            con.execute("SELECT 1 FROM revlog LIMIT 1").fetchall()
        finally:
            con.close()
    except sqlite3.DatabaseError:
        # Not SQLite at all ("file is not a database"), or SQLite without a
        # revlog table (OperationalError is a DatabaseError subclass).
        raise SystemExit(
            f"{shown_path} is not a valid Anki collection "
            "(expected collection.anki2 or a .colpkg bundle)."
        )


def main() -> None:
    args = _parse_args()
    collection = _find_collection(args.collection)
    shown_collection = collection

    # Handle .colpkg files: extract to temp SQLite file
    temp_colpkg_path = None
    if collection.suffix == ".colpkg":
        try:
            temp_colpkg_path = _extract_colpkg_to_sqlite(collection)
            collection = temp_colpkg_path
        except SystemExit:
            raise
        except Exception as e:
            raise SystemExit(f"Failed to extract .colpkg: {e}")

    try:
        _validate_collection(collection, shown_collection)

        # --list-templates: print and exit (after extraction, so it also
        # works on .colpkg bundles)
        if args.list_templates:
            _list_templates(collection, show_all=args.show_all_templates)
            return

        # Export reviews (always)
        export_reviews(
            collection, args.output,
            deck_filter=args.deck,
            since=args.since,
            vocab_dir=args.vocab_dir,
            append=args.append,
        )

        # Export card snapshot (optional)
        if args.card_snapshot:
            snapshot_path = args.card_snapshot_output or (
                args.output.with_stem(args.output.stem + ".cards")
            )
            export_card_snapshot(collection, snapshot_path, deck_filter=args.deck)
    finally:
        # Clean up temp extracted file
        if temp_colpkg_path is not None:
            tmp_parent = temp_colpkg_path.parent
            if tmp_parent.exists():
                shutil.rmtree(tmp_parent, ignore_errors=True)


if __name__ == "__main__":
    main()
