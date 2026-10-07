import pandas as pd
import pytest

from zhongwen_anki.build_all import build_all
from zhongwen_anki.enrich import REQUIRED_COLS


def _write_level(data_dir, level, rows):
    (data_dir / level).mkdir(parents=True)
    pd.DataFrame(rows, columns=REQUIRED_COLS).to_csv(data_dir / level / "input.tsv", sep="\t", index=False)


ROW = ["你好", "你好", "nǐ hǎo", "hello", "你好。", "Hello.", "", "问候语", "greeting"]


def test_build_all_builds_every_level_found(tmp_path):
    data_dir, decks_dir = tmp_path / "data", tmp_path / "decks"
    _write_level(data_dir, "hsk1", [ROW])
    _write_level(data_dir, "hsk2", [ROW])

    written = build_all(data_dir=data_dir, decks_dir=decks_dir)

    assert [p.name for p in written] == ["HSK1.apkg", "HSK2.apkg"]
    assert all(p.exists() for p in written)
    assert (data_dir / "hsk2" / "output.tsv").exists()


def test_build_all_can_build_selected_levels(tmp_path):
    data_dir, decks_dir = tmp_path / "data", tmp_path / "decks"
    _write_level(data_dir, "hsk1", [ROW])
    _write_level(data_dir, "hsk2", [ROW])

    written = build_all(["hsk2"], data_dir=data_dir, decks_dir=decks_dir)

    assert [p.name for p in written] == ["HSK2.apkg"]


def test_build_all_rejects_a_level_without_input(tmp_path):
    data_dir = tmp_path / "data"
    _write_level(data_dir, "hsk1", [ROW])
    with pytest.raises(SystemExit):
        build_all(["HSK3"], data_dir=data_dir, decks_dir=tmp_path / "decks")
