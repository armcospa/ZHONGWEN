import html
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional

import jieba
from pypinyin import Style, pinyin as _pinyin
from pypinyin.contrib.tone_convert import to_normal
from pypinyin.pinyin_dict import pinyin_dict

# Combining diacritics of the four pinyin tones (in NFD form).
_TONE_BY_MARK = {"̄": 1, "́": 2, "̌": 3, "̀": 4}
_DIAERESIS = "̈"
_LETTERS_RE = re.compile(r"[^\W\d_]+")


@lru_cache(maxsize=1)
def _pinyin_syllables() -> frozenset:
    """Every valid toneless pinyin syllable (with ü), e.g. "zhuang", "lü", "ng"."""
    # pypinyin spells ü as "v" in its toneless form (lv, nve).
    return frozenset(
        to_normal(reading).replace("v", "ü")
        for readings in pinyin_dict.values()
        for reading in readings.split(",")
    )


def _split_tones(word: str) -> tuple:
    """"Àihào" -> ("Aihao", [4, 0, 0, 0, 4, 0]): letters without tone marks
    (keeping ü) and the tone carried by each letter (0 = none)."""
    letters, tones = [], []
    for char in word:
        base, *marks = unicodedata.normalize("NFD", char)
        if _DIAERESIS in marks:
            base = unicodedata.normalize("NFC", base + _DIAERESIS)
        letters.append(base)
        tones.append(next((_TONE_BY_MARK[m] for m in marks if m in _TONE_BY_MARK), 0))
    return "".join(letters), tones


def _segment(letters: str, tones: List[int]) -> Optional[List[tuple]]:
    """Split toneless *letters* into valid syllables, as (start, end) pairs.

    Among all segmentations, the one with the fewest syllables wins, with two
    constraints that make it unambiguous for well-formed pinyin: at most one
    tone mark per syllable, and no syllable starting with a/o/e except at the
    start of the word (pinyin writes an apostrophe there: fāng'àn, xī'ān).
    Erhua (wánr) is a valid syllable followed by "r"."""
    syllables = _pinyin_syllables()
    lower = letters.lower()
    n = len(lower)
    best: List[Optional[List[tuple]]] = [None] * (n + 1)
    best[0] = []
    for end in range(1, n + 1):
        for start in range(max(0, end - 7), end):
            if best[start] is None:
                continue
            piece = lower[start:end]
            erhua = len(piece) > 1 and piece.endswith("r") and piece[:-1] in syllables and piece != "er"
            if piece not in syllables and not erhua:
                continue
            if start > 0 and piece[0] in "aoe":
                continue
            if sum(1 for t in tones[start:end] if t) > 1:
                continue
            candidate = best[start] + [(start, end)]
            if best[end] is None or len(candidate) < len(best[end]):
                best[end] = candidate
    return best[n]


def pinyin_to_numbered(pinyin: str) -> str:
    """Rewrite tone-marked pinyin with tone numbers after each syllable.

    "àihào" -> "ai4hao4", "bà ba" -> "ba4 ba5", "Xī'ān" -> "Xi1'an1",
    "lǜsè" -> "lü4se4", "hǎo wánr" -> "hao3 wanr2". The neutral tone is 5
    (as in CC-CEDICT). Spaces, apostrophes and hyphens are kept as they are.
    Returns "" if some part can't be split into valid syllables.
    """
    pinyin = unicodedata.normalize("NFC", pinyin)
    out = []
    last = 0
    for match in _LETTERS_RE.finditer(pinyin):
        out.append(pinyin[last:match.start()])
        letters, tones = _split_tones(match.group())
        segments = _segment(letters, tones)
        if segments is None:
            return ""
        for start, end in segments:
            tone = max(tones[start:end])
            out.append(letters[start:end] + str(tone or 5))
        last = match.end()
    out.append(pinyin[last:])
    return "".join(out)


@dataclass(slots=True)
class Character:
    pinyin: str
    hanzi: str
    tone: int  # 1‒5 (5 = neutral)

    @property
    def hanzi_marked(self) -> str:
        """Return `<mark class="toneN">char</mark>` with N = self.tone."""
        return f'<mark class="tone-{self.tone}">{html.escape(self.hanzi)}</mark>'


@dataclass(slots=True)
class Word:
    raw: str
    is_chinese: bool
    parts: List[Character | str]

    def __iter__(self):
        return iter(self.parts)

def _is_chinese_character(ch: str) -> bool:
    """Return *True* iff *ch* is in any UCS block that contains Hanzi."""
    ranges = (
        ("\u4E00", "\u9FFF"),   # CJK Unified Ideographs
        ("\u3400", "\u4DBF"),   # Extension A
        ("\u20000", "\u2A6DF"), # Extension B
        ("\u2A700", "\u2B73F"), # Extension C
        ("\u2B740", "\u2B81F"), # Extension D
        ("\u2B820", "\u2CEAF"), # Extension E
        ("\u2CEB0", "\u2EBEF"), # Extension F
        ("\uF900", "\uFAFF"),   # Compatibility Ideographs
    )
    return any(start <= ch <= end for start, end in ranges)


def _tone_from_numbered_tone(pinyin: str) -> int:
    """Extract the final digit of a TONE3 syllable; neutral → 5."""
    for c in reversed(pinyin):
        if c.isdigit():
            return int(c)
    return 5  # neutral / fifth tone


def sentence_to_words(
    sentence_text: str,
) -> List[Word]:
    """
    Segment *sentence_text* into a flat list[Word] while keeping the
    pinyin database *aligned character-for-character* with the original
    string.

    1.  Run **pypinyin on the whole sentence** so the model
        disambiguates polyphonic characters by context.
    2.  Pass `errors=lambda s: list(s)` so *each* non-Hanzi character
        becomes its own one-element group, keeping perfect 1-to-1
        alignment between the returned list and the source string.
    3.  Use the same cursor to walk through both the pinyin list and
        Jieba’s tokens, so every Hanzi ends up with the syllable pypinyin
        has already chosen.
    """
    if not sentence_text or not sentence_text.strip():
        return []

    # --- 1 · pinyin for the whole sentence --------------------------------
    pinyin_marks = _pinyin(
        sentence_text,
        style=Style.TONE,        # marks: hǎo
        heteronym=False,
        errors=lambda bad: list(bad),   # 1 group per char
    )
    pinyin_nums = _pinyin(
        sentence_text,
        style=Style.TONE3,       # numbers: hao3
        heteronym=False,
        errors=lambda bad: list(bad),
    )
    # flatten (one string per original character)
    pinyin_marks = [grp[0] for grp in pinyin_marks]
    pinyin_nums  = [grp[0] for grp in pinyin_nums]

    # --- 2 · Jieba segmentation ------------------------------------------
    tokens = [tok for tok in jieba.lcut(sentence_text) if tok]

    words: List[Word] = []
    idx = 0          # cursor into pinyin_* lists

    for tok in tokens:
        if any(_is_chinese_character(c) for c in tok):
            # ---------------- Chinese word ----------------
            parts: List[Character] = []
            for ch in tok:
                py_mark = pinyin_marks[idx]
                py_num  = pinyin_nums[idx]
                parts.append(
                    Character(
                        pinyin=py_mark,
                        hanzi=ch,
                        tone=_tone_from_numbered_tone(py_num),
                    )
                )
                idx += 1
            words.append(Word(raw=tok, is_chinese=True, parts=parts))
        else:
            # ---------------- non-Chinese token ----------------
            words.append(Word(raw=tok, is_chinese=False, parts=[tok]))
            idx += len(tok)   # advance by number of characters

    return words


def words_to_hanzi(words: List[Word], sep: str="") -> str:
    """Concatenate `word.raw` across the list."""
    return sep.join(word.raw for word in words)


def words_to_pinyin(
    words: List[Word],
    *,
    char_sep: str = "",
    word_sep: str = " ",
) -> str:
    """
    Convert *words* to a pinyin string.

    Parameters
    ----------
    char_sep :
        Separator inserted **between syllables inside the same Chinese word**.
        The default (“”) glues the syllables together.
    word_sep :
        Separator inserted **between words** (Chinese or otherwise).
        The default is a single space.

    Returns
    -------
    str
        The pinyin representation with tone marks; non-Chinese substrings
        are preserved verbatim.

    Notes
    -----
    • Setting *char_sep* and *word_sep* to the same value reproduces the
      original behaviour.
    • Example:
        `words_to_pinyin(words, char_sep="", word_sep=" ")`
        → `"ni shi wo de pengyou"`
    """
    result = ""
    glue_next = True  # no separator before the first segment
    for word in words:
        if word.is_chinese:
            segment = char_sep.join(char.pinyin for char in word.parts)  # type: ignore[arg-type]
        elif not word.raw.strip():
            continue  # whitespace: word_sep already separates segments
        else:
            segment = word.raw
        categories = {unicodedata.category(c) for c in segment}
        is_punctuation = all(cat.startswith("P") for cat in categories)
        opening = is_punctuation and categories <= {"Ps", "Pi"}
        # Punctuation sticks to the previous word ("wǒ de。", not "wǒ de 。"),
        # and opening brackets/quotes to the next one.
        if not (glue_next or (is_punctuation and not opening)):
            result += word_sep
        result += segment
        glue_next = opening
    return result


def words_to_colored_hanzi(
    words: List[Word], *, sep: str = "", escape_non_chinese: bool = True
) -> str:
    """Return `sentence_text` where every Hanzi is wrapped in <mark class="tone-N">.

    *sep* joins the converted segments – use a single space for sentence &
    dictionary fields, and empty string for headwords.  If *escape_non_chinese*
    is False, non-Chinese substrings are inserted verbatim (useful for the
    synonym field which already contains its own HTML & punctuation).
    """
    rendered: List[str] = []
    for word in words:
        if word.is_chinese:
            rendered.append("".join(char.hanzi_marked for char in word.parts))  # type: ignore[arg-type]
        else:
            rendered.append(html.escape(word.raw) if escape_non_chinese else word.raw)
    return sep.join(rendered)


def process_synonyms(synonym_string: str) -> str:
    """Colour‑mark the Hanzi in a `<br>`‑separated synonyms string **without**
    altering any punctuation or existing HTML tags.

    Example input
        "矢量 (shǐ liàng) - vector<br>量向 (liàng xiàng) - vector"

    Returns the same string with Hanzi wrapped in `<mark class="toneN">…</mark>`.
    """
    if not synonym_string:
        return ""

    entries = synonym_string.split("<br>")
    colored_entries: List[str] = []

    for entry in entries:
        words = sentence_to_words(entry)
        colored_entries.append(words_to_colored_hanzi(words, escape_non_chinese=False))

    return "<br>".join(colored_entries)


if __name__ == '__main__':

    def debug_word_repr(words):
        repr_lines = []
        for w in words:
            if w.is_chinese:
                chars_info = ",".join(f"{c.hanzi}({c.pinyin},{c.tone})" for c in w.parts)  # type: ignore[arg-type]
                repr_lines.append(f"CN[{chars_info}]")
            else:
                repr_lines.append(f"TXT[{w.raw}]")
        return " | ".join(repr_lines)


    examples = [
        "你好世界",
        "你好，世界！",
        "我喜欢Python和C++。",
        "你好   世界",
        "  leading and trailing spaces  ",
        "你好，世界！123 numbers"
    ]

    outputs = []

    for sent in examples:
        words = sentence_to_words(sent)
        outputs.append({
            "Sentence": sent,
            "WordList": debug_word_repr(words),
            "Simplified": words_to_hanzi(words),
            "Pinyin": words_to_pinyin(words),
            "HTML": words_to_colored_hanzi(words)
        })

    import pandas as pd

    df = pd.DataFrame(outputs)
    print(df)

