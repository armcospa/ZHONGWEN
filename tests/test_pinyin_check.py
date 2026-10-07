"""Run the typed-pinyin checker of the card templates (JavaScript) with Node.

Skipped when Node isn't installed. Checks the answer normalization against
every word of every level: tone numbers, tone marks and spacing variants
must be accepted, and a wrong tone must not.
"""
import json
import re
import shutil
import subprocess

import pandas as pd
import pytest

from zhongwen_anki.build_deck import SHARED_DIR
from zhongwen_anki.hanzi_writer import discover_input_tsvs
from zhongwen_anki.utilities import pinyin_to_numbered

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _run_checker(cases):
    """Evaluate *cases* ([typed, expected] pairs) with the template's
    canonical(): returns whether each pair is accepted."""
    html = (SHARED_DIR / "pinyin_check.html").read_text(encoding="utf-8")
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    program = (
        "var window = {}; var document = {getElementById: function () { return null; }};\n"
        + script
        + "\nvar cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
        + "process.stdout.write(JSON.stringify(cases.map(function (c) {\n"
        + "  return window.zhongwenPinyin.canonical(c[0]) === window.zhongwenPinyin.canonical(c[1]);\n"
        + "})));\n"
    )
    result = subprocess.run(
        [NODE, "-e", program], input=json.dumps(cases), capture_output=True, text=True, encoding="utf-8", check=True
    )
    return json.loads(result.stdout)


def _all_pinyin():
    return [p for tsv in discover_input_tsvs() for p in pd.read_csv(tsv, sep="\t", dtype=str)["Pinyin"]]


def test_tone_numbers_are_accepted_for_every_word():
    words = _all_pinyin()
    cases = [[pinyin_to_numbered(p), p] for p in words]
    accepted = _run_checker(cases)
    rejected = [c for c, ok in zip(cases, accepted) if not ok]
    assert rejected == []


def test_tone_marks_spacing_and_case_variants_are_accepted():
    cases = [
        ["àihào", "àihào"],
        ["ài hào", "àihào"],
        ["bàba", "bà ba"],
        ["AI4HAO4", "àihào"],
        ["ai4 hao4", "àihào"],
        ["lv4se4", "lǜsè"],
        ["lu:4se4", "lǜsè"],
        ["nü3'er2", "nǚ'ér"],
        ["ba4ba5", "bà ba"],
        ["ba4ba0", "bà ba"],
        ["ba4ba", "bà ba"],
        ["ng4", "ǹg"],
        ["xi1an1", "xī'ān"],
        ["hong2lv4deng1", "hóng-lǜdēng"],
        ["gui4", "guì"],
        ["liu2", "liú"],
        ["zhou1", "zhōu"],
        ["hao3 wanr2", "hǎo wánr"],
    ]
    assert _run_checker(cases) == [True] * len(cases)


def test_wrong_tones_or_letters_are_rejected():
    cases = [
        ["ai4hao3", "àihào"],
        ["àihǎo", "àihào"],
        ["aihao", "àihào"],
        ["ai4hao", "àihào"],
        ["lu4se4", "lǜsè"],
        ["bao4", "bà"],
    ]
    assert _run_checker(cases) == [False] * len(cases)


def test_neutral_tone_numbers_can_be_omitted():
    cases = [["lai2deji2", "láidejí"], ["lai2de5ji2", "láidejí"], ["xian1sheng", "xiānsheng"]]
    assert _run_checker(cases) == [True] * len(cases)


def test_template_syllable_list_matches_the_python_one():
    from zhongwen_anki.utilities import _pinyin_syllables

    html = (SHARED_DIR / "pinyin_check.html").read_text(encoding="utf-8")
    listed = re.search(r"var SYLLABLE_LIST = '([^']*)'", html).group(1).split(" ")
    assert set(listed) == set(_pinyin_syllables())
