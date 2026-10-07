"""Build the self-contained HanziWriter <script> block for the hanzi-writing cards.

The PM2H, M2H and P2H cards draw characters stroke by stroke with
HanziWriter. Its source and every needed character's stroke data are
inlined directly into the card templates as static content, rather than
loaded from external files at runtime, because Anki's webview has a known
race condition where external <script src="..."> / fetch()'d media files
aren't always loaded in time when a card's own inline script runs (worse on
AnkiDroid).

The block is built in memory by build_deck (through the
`<!-- include: hanzi_writer -->` marker in the card templates), so there is
no generated file to keep in sync. The note type is shared across every HSK
level, so it embeds the union of characters used across every
data/<level>/input.tsv, plus any extra characters passed in.
"""
from functools import lru_cache
import json
from pathlib import Path
from typing import Iterable, List

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
HANZI_WRITER_DIR = ROOT_DIR / "vendor" / "hanzi-writer"
DATA_DIR = ROOT_DIR / "data"


def discover_input_tsvs(data_dir: Path = DATA_DIR) -> List[Path]:
    """Every data/<level>/input.tsv found on disk, e.g. data/hsk1/input.tsv."""
    return sorted(data_dir.glob("*/input.tsv"))


def used_characters(input_tsvs: Iterable[Path]) -> set:
    chars = set()
    for tsv in input_tsvs:
        df = pd.read_csv(tsv, sep="\t", dtype=str)
        for word in df["Simplified"].dropna():
            chars.update(word)
    return chars


def bundle_html(chars: Iterable[str], assets_dir: Path = HANZI_WRITER_DIR) -> str:
    """Return the HanziWriter library and the stroke data of *chars* as two
    inline <script> blocks. Raises SystemExit if any character has no
    stroke data in *assets_dir*/data."""
    return _bundle_html(frozenset(chars), assets_dir)


@lru_cache(maxsize=4)
def _bundle_html(chars: frozenset, assets_dir: Path) -> str:
    lib_js = (assets_dir / "hanzi-writer.min.js").read_text(encoding="utf-8")
    lib_js = "\n".join(
        line for line in lib_js.splitlines() if not line.strip().startswith("//# sourceMappingURL")
    )

    data_dir = assets_dir / "data"
    combined = {}
    missing = []
    for char in sorted(chars):
        path = data_dir / f"{char}.json"
        if path.exists():
            combined[char] = json.loads(path.read_text(encoding="utf-8"))
        else:
            missing.append(char)
    if missing:
        raise SystemExit(
            f"Missing stroke data for {len(missing)} character(s): {''.join(missing)}\n"
            f"Add <char>.json for each to {data_dir} (see NOTICE.md for how to get them)."
        )

    data_blob = "var HANZI_DATA = " + json.dumps(combined, ensure_ascii=False, separators=(",", ":")) + ";"
    return f"<script>\n{lib_js}\n</script>\n\n<script>\n{data_blob}\n</script>\n"
