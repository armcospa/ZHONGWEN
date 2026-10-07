import pandas as pd
import pytest

from zhongwen_anki import hanzi_writer


def test_used_characters_returns_unique_chars_across_all_words(tmp_path):
    tsv = tmp_path / "input.tsv"
    pd.DataFrame({"Simplified": ["你好", "谢谢"]}).to_csv(tsv, sep="\t", index=False)

    assert hanzi_writer.used_characters([tsv]) == set("你好谢")


def test_used_characters_merges_across_multiple_levels(tmp_path):
    """The note type is shared across HSK levels, so the character set fed
    into the hanzi-writing cards must be the union across every
    data/<level>/input.tsv, not just one level."""
    hsk1 = tmp_path / "hsk1.tsv"
    hsk2 = tmp_path / "hsk2.tsv"
    pd.DataFrame({"Simplified": ["你好"]}).to_csv(hsk1, sep="\t", index=False)
    pd.DataFrame({"Simplified": ["谢谢"]}).to_csv(hsk2, sep="\t", index=False)

    assert hanzi_writer.used_characters([hsk1, hsk2]) == set("你好谢")


def test_discover_input_tsvs_finds_one_per_level(tmp_path):
    for level in ("hsk1", "hsk2"):
        (tmp_path / level).mkdir()
        (tmp_path / level / "input.tsv").write_text("Simplified\n", encoding="utf-8")
    (tmp_path / "hsk2" / "output.tsv").write_text("", encoding="utf-8")

    found = hanzi_writer.discover_input_tsvs(tmp_path)
    assert [p.parent.name for p in found] == ["hsk1", "hsk2"]


def test_bundle_embeds_the_library_and_only_the_needed_characters():
    bundle = hanzi_writer.bundle_html("你好")
    assert "HanziWriter" in bundle
    assert "HANZI_DATA" in bundle
    assert '"你"' in bundle
    assert '"好"' in bundle
    assert '"谢"' not in bundle
    assert "sourceMappingURL" not in bundle


def test_bundle_raises_when_stroke_data_is_missing(tmp_path):
    assets = tmp_path / "hanzi_writer"
    (assets / "data").mkdir(parents=True)
    lib = hanzi_writer.HANZI_WRITER_DIR / "hanzi-writer.min.js"
    (assets / "hanzi-writer.min.js").write_text(lib.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(SystemExit):
        hanzi_writer.bundle_html("龘", assets_dir=assets)


def test_every_character_in_the_vocabulary_has_stroke_data():
    chars = hanzi_writer.used_characters(hanzi_writer.discover_input_tsvs())
    missing = [c for c in chars if not (hanzi_writer.HANZI_WRITER_DIR / "data" / f"{c}.json").exists()]
    assert missing == []
