import pandas as pd
import pytest

from zhongwen_anki import build_hanzi_templates as bht


def test_used_characters_returns_unique_chars_across_all_words(tmp_path):
    tsv = tmp_path / "input.tsv"
    pd.DataFrame({"Simplified": ["你好", "谢谢"]}).to_csv(tsv, sep="\t", index=False)

    assert bht._used_characters([tsv]) == set("你好谢")


def test_used_characters_merges_across_multiple_levels(tmp_path):
    """The note type is shared across HSK levels, so the character set fed
    into the shared hanzi_writing template must be the union across every
    data/<level>/input.tsv, not just one level."""
    hsk1 = tmp_path / "hsk1.tsv"
    hsk2 = tmp_path / "hsk2.tsv"
    pd.DataFrame({"Simplified": ["你好"]}).to_csv(hsk1, sep="\t", index=False)
    pd.DataFrame({"Simplified": ["谢谢"]}).to_csv(hsk2, sep="\t", index=False)

    assert bht._used_characters([hsk1, hsk2]) == set("你好谢")


def _copy_real_assets(tmp_path, chars):
    """Build a throwaway hanzi_writing dir with just the given characters,
    so tests never write over the real, checked-in front.html/back.html."""
    fake_dir = tmp_path / "hanzi_writing"
    fake_data_dir = fake_dir / "data"
    fake_data_dir.mkdir(parents=True)

    real_lib = bht.HANZI_DIR / "hanzi-writer.min.js"
    (fake_dir / "hanzi-writer.min.js").write_text(real_lib.read_text(encoding="utf-8"), encoding="utf-8")

    for char in chars:
        src = bht.HANZI_DIR / "data" / f"{char}.json"
        (fake_data_dir / f"{char}.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    return fake_dir


def test_build_embeds_only_the_needed_characters(tmp_path, monkeypatch):
    fake_dir = _copy_real_assets(tmp_path, "你好")
    tsv = tmp_path / "input.tsv"
    pd.DataFrame({"Simplified": ["你好"]}).to_csv(tsv, sep="\t", index=False)

    monkeypatch.setattr(bht, "HANZI_DIR", fake_dir)

    bht.build([tsv])

    front = (fake_dir / "front.html").read_text(encoding="utf-8")
    back = (fake_dir / "back.html").read_text(encoding="utf-8")
    for content in (front, back):
        assert "HANZI_DATA" in content
        assert '"你"' in content
        assert '"好"' in content
        assert "{{Simplified}}" in content
        assert "HanziWriter" in content


def test_build_merges_characters_from_every_discovered_level(tmp_path, monkeypatch):
    fake_dir = _copy_real_assets(tmp_path, "你好")
    hsk1 = tmp_path / "hsk1.tsv"
    hsk2 = tmp_path / "hsk2.tsv"
    pd.DataFrame({"Simplified": ["你"]}).to_csv(hsk1, sep="\t", index=False)
    pd.DataFrame({"Simplified": ["好"]}).to_csv(hsk2, sep="\t", index=False)

    monkeypatch.setattr(bht, "HANZI_DIR", fake_dir)

    bht.build([hsk1, hsk2])

    front = (fake_dir / "front.html").read_text(encoding="utf-8")
    assert '"你"' in front
    assert '"好"' in front


def test_build_raises_when_stroke_data_is_missing(tmp_path, monkeypatch):
    fake_dir = _copy_real_assets(tmp_path, "")  # no character data at all
    tsv = tmp_path / "input.tsv"
    pd.DataFrame({"Simplified": ["龘"]}).to_csv(tsv, sep="\t", index=False)

    monkeypatch.setattr(bht, "HANZI_DIR", fake_dir)

    with pytest.raises(SystemExit):
        bht.build([tsv])


def test_build_raises_when_no_input_tsvs_are_found_or_given(tmp_path, monkeypatch):
    monkeypatch.setattr(bht, "DATA_DIR", tmp_path)  # empty dir, no data/*/input.tsv

    with pytest.raises(SystemExit):
        bht.build()
