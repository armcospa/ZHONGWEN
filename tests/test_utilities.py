import pytest

from zhongwen_anki.utilities import (
    process_synonyms,
    sentence_to_words,
    words_to_colored_hanzi,
    words_to_hanzi,
    words_to_pinyin,
    pinyin_to_numbered,
)


def test_words_to_hanzi_roundtrips_original_text():
    words = sentence_to_words("你好，世界！")
    assert words_to_hanzi(words) == "你好，世界！"


def test_words_to_pinyin_produces_syllables():
    words = sentence_to_words("你好")
    pinyin = words_to_pinyin(words)
    assert pinyin
    assert "n" in pinyin.lower()


def test_words_to_colored_hanzi_wraps_each_character_in_a_tone_mark():
    words = sentence_to_words("你好")
    html = words_to_colored_hanzi(words)
    assert html.count('<mark class="tone-') == 2
    assert "你" in html and "好" in html


def test_sentence_to_words_keeps_non_chinese_tokens_separate():
    words = sentence_to_words("Hello 你好")
    assert any(not w.is_chinese for w in words)
    assert any(w.is_chinese for w in words)


def test_sentence_to_words_empty_string_returns_empty_list():
    assert sentence_to_words("") == []
    assert sentence_to_words("   ") == []


def test_process_synonyms_colors_hanzi_but_keeps_surrounding_text():
    raw = "喜欢 (xǐ huan) - to like<br>爱 (ài) - to love"
    colored = process_synonyms(raw)
    assert "<br>" in colored
    assert "(xǐ huan)" in colored
    assert "- to like" in colored
    assert '<mark class="tone-' in colored


def test_process_synonyms_empty_string_returns_empty_string():
    assert process_synonyms("") == ""


@pytest.mark.parametrize("marked, numbered", [
    ("àihào", "ai4hao4"),
    ("bà ba", "ba4 ba5"),
    ("Yàzhōu", "Ya4zhou1"),
    ("xī'ān", "xi1'an1"),
    ("lǜsè", "lü4se4"),
    ("nǚ'ér", "nü3'er2"),
    ("hóng-lǜdēng", "hong2-lü4deng1"),
    ("hǎo wánr", "hao3 wanr2"),
    ("ǹg", "ng4"),
    ("láidejí", "lai2de5ji2"),
    ("fāng'àn", "fang1'an4"),
])
def test_pinyin_to_numbered(marked, numbered):
    assert pinyin_to_numbered(marked) == numbered


def test_pinyin_to_numbered_returns_empty_for_non_pinyin():
    assert pinyin_to_numbered("qwrtz") == ""


def test_words_to_pinyin_attaches_punctuation_to_the_previous_word():
    pinyin = words_to_pinyin(sentence_to_words("他说：“你好！”我们走吧。"))
    assert " 。" not in pinyin and " ！" not in pinyin and " ：" not in pinyin
    assert pinyin.endswith("ba。")
    assert "“nǐhǎo！”" in pinyin
