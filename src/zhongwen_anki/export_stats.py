"""Export Anki's review history (revlog) to a clean CSV for external analysis.

Reads directly from the local collection.anki2 SQLite file (opened read-only,
so it's safe even while Anki is running) and writes one row per review ever
done, joined with the deck name and the note's first field (the Chinese word).

Usage:
    python -m zhongwen_anki.export_stats
    python -m zhongwen_anki.export_stats --deck "HSK1" -o data/anki_reviews.csv
    python -m zhongwen_anki.export_stats --collection "C:\\path\\to\\collection.anki2"

Notes on the Anki schema (kept raw on purpose, for faithful downstream analysis):
    - `interval` / `last_interval`: positive = days, negative = seconds
      (Anki uses seconds for the short intervals during learning steps).
    - `ease_factor_percent`: 250 means the interval multiplies by 2.5 on a
      correct review.
    - `is_correct` is a simple heuristic: ease >= 2 (i.e. not "Again").
"""
import argparse
import csv
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

EASE_LABELS = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
REVIEW_TYPE_LABELS = {0: "learning", 1: "review", 2: "relearning", 3: "cram/filtered", 4: "manual"}


def _default_collection_candidates():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    base = Path(appdata) / "Anki2"
    if not base.exists():
        return []
    return sorted(base.glob("*/collection.anki2"))


def _find_collection(explicit: Optional[Path]) -> Path:
    if explicit is not None:
        if not explicit.exists():
            raise SystemExit(f"Collection file not found: {explicit}")
        return explicit

    candidates = _default_collection_candidates()
    if not candidates:
        raise SystemExit(
            "Could not auto-detect an Anki collection under %APPDATA%\\Anki2.\n"
            "Close Anki and pass --collection <path to collection.anki2> explicitly."
        )
    if len(candidates) > 1:
        listing = "\n".join(f"  - {c}" for c in candidates)
        raise SystemExit(
            "Multiple Anki profiles found; pass --collection to pick one:\n" + listing
        )
    return candidates[0]


def export(collection_path: Path, output_path: Path, deck_filter: Optional[str]) -> None:
    uri = f"file:{collection_path.as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row

    # Modern Anki (schema 18+) stores decks in their own table; older
    # collections keep them as a JSON blob on the `col` row. Support both.
    try:
        decks = {row["id"]: row["name"] for row in con.execute("SELECT id, name FROM decks")}
    except sqlite3.OperationalError:
        decks_raw = con.execute("SELECT decks FROM col").fetchone()["decks"]
        decks = {int(k): v["name"] for k, v in json.loads(decks_raw).items()}

    rows = con.execute(
        """
        SELECT revlog.id AS review_epoch_ms, revlog.cid AS card_id, revlog.ease,
               revlog.ivl AS interval, revlog.lastIvl AS last_interval,
               revlog.factor AS factor, revlog.time AS time_ms, revlog.type AS review_type,
               cards.did AS deck_id, cards.odid AS orig_deck_id, cards.nid AS note_id,
               notes.flds AS flds
        FROM revlog
        JOIN cards ON cards.id = revlog.cid
        JOIN notes ON notes.id = cards.nid
        ORDER BY revlog.id
        """
    ).fetchall()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "review_datetime", "deck", "note_id", "card_id", "word",
            "ease", "ease_label", "is_correct",
            "interval", "last_interval", "ease_factor_percent",
            "time_seconds", "review_type",
        ])
        for row in rows:
            # If a card is currently sitting in a filtered/cram deck, `did`
            # points at that temporary deck and the real ("home") deck is in
            # `odid` instead. Prefer the home deck so stats aren't attributed
            # to a filtered deck that may not even exist anymore by the time
            # this export runs.
            home_deck_id = row["orig_deck_id"] or row["deck_id"]
            deck_name = decks.get(home_deck_id, "")
            if deck_filter and deck_filter.lower() not in deck_name.lower():
                continue
            word = row["flds"].split("\x1f")[0]
            writer.writerow([
                datetime.fromtimestamp(row["review_epoch_ms"] / 1000).isoformat(sep=" ", timespec="seconds"),
                deck_name,
                row["note_id"],
                row["card_id"],
                word,
                row["ease"],
                EASE_LABELS.get(row["ease"], row["ease"]),
                int(row["ease"] >= 2),
                row["interval"],
                row["last_interval"],
                round(row["factor"] / 10, 1) if row["factor"] else "",
                round(row["time_ms"] / 1000, 1),
                REVIEW_TYPE_LABELS.get(row["review_type"], row["review_type"]),
            ])
            written += 1

    print(f"Wrote {written:,} reviews -> {output_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Anki review history (revlog) to CSV.")
    parser.add_argument("--collection", type=Path, default=None,
                         help="Path to collection.anki2 (auto-detected under %%APPDATA%%\\Anki2 if omitted).")
    parser.add_argument("-o", "--output", type=Path, default=Path("data/anki_reviews.csv"))
    parser.add_argument("--deck", type=str, default=None,
                         help="Only include reviews from decks whose name contains this text.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    collection = _find_collection(args.collection)
    export(collection, args.output, args.deck)


if __name__ == "__main__":
    main()
