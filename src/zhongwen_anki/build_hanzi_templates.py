"""Regenerate card_template/hanzi_writing/{front,back}.html.

These two files are checked in fully self-contained (HanziWriter's source and
every character's stroke data inlined directly as static content), rather
than loaded from external files at runtime, because Anki's webview has a
known race condition where external <script src="..."> / fetch()'d media
files aren't always loaded in time when a card's own inline script runs
(worse on AnkiDroid). Re-run this whenever the character set changes (e.g.
after adding a new HSK level's vocabulary) or the HanziWriter library is
upgraded.

The note type is shared across every HSK level, so by default this scans
every data/<level>/input.tsv it can find and embeds the union of characters
used across all of them -- one regeneration covers every deck you build.

Usage:
    python -m zhongwen_anki.build_hanzi_templates
    python -m zhongwen_anki.build_hanzi_templates -i data/hsk1/input.tsv data/hsk2/input.tsv
"""
import argparse
import json
from pathlib import Path
from typing import List, Optional

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
HANZI_DIR = ROOT_DIR / "card_template" / "hanzi_writing"
DATA_DIR = ROOT_DIR / "data"

# Static page content around the generated <script> blocks. Plain text,
# concatenated as-is (no .format()) — keep this in sync by hand if you want
# to redesign the card layout, then re-run this script.
FRONT_BODY = """\
<div class=pinyin>{{Pinyin}}&nbsp<br></div>
<div class=meaning>{{MeaningES}} <span class=en-secondary>({{Meaning}})</span>&nbsp<br></div>
<div style="line-height:50%;"><br></div>

<hr>

<div id="hanziQuizBox" data-word="{{Simplified}}" style="display:flex; overflow-x:auto; border:2px solid #999; background:#fff; margin:10px auto 0 auto; width:fit-content; max-width:100%;"></div>
<div id="hanziQuizStatus" style="text-align:center; font-family: Georgia; font-size:14px; color:grey; margin-top:6px;">Dibuja cada trazo con el ratón o el dedo.</div>

<script>
function _hanziQuizInit() {
    var container = document.getElementById('hanziQuizBox');
    var status = document.getElementById('hanziQuizStatus');
    if (!container) return;
    var word = container.getAttribute('data-word');
    var chars = Array.from(word);
    var total = chars.length;
    var done = 0;
    var mistakes = 0;
    var cellSize = 170;

    function loader(char, onLoad, onError) {
        var data = (typeof HANZI_DATA !== 'undefined') ? HANZI_DATA[char] : null;
        if (data) {
            onLoad(data);
        } else if (onError) {
            onError('missing data for ' + char);
        }
    }

    chars.forEach(function (char, i) {
        var cell = document.createElement('div');
        cell.id = 'hanziCell' + i;
        cell.style.width = cellSize + 'px';
        cell.style.height = cellSize + 'px';
        cell.style.flex = '0 0 auto';
        cell.style.touchAction = 'none';
        cell.style.userSelect = 'none';
        if (i > 0) cell.style.borderLeft = '1px dashed #ccc';
        container.appendChild(cell);

        var writer = HanziWriter.create(cell.id, char, {
            width: cellSize,
            height: cellSize,
            padding: 5,
            showCharacter: false,
            showOutline: false,
            strokeAnimationSpeed: 1,
            delayBetweenStrokes: 100,
            charDataLoader: loader,
        });

        writer.quiz({
            onComplete: function (summary) {
                done += 1;
                mistakes += summary.totalMistakes;
                status.innerText = done + ' / ' + total + ' caracteres completados (fallos totales: ' + mistakes + ')';
            },
        });
    });
}
// Some Anki webviews (notably AnkiDroid) may run this inline script before
// the page/DOM is fully settled. Deferring to the 'load' event, following
// the pattern used by github.com/krmanik/Anki-xiehanzi, avoids that race.
if (document.readyState === 'complete') {
    _hanziQuizInit();
} else {
    window.addEventListener('load', _hanziQuizInit);
}
</script>
"""

BACK_BODY = """\
<div class=mainCharacters>{{Traditional}}&nbsp<br></div>
<div class=secondaryCharactersColored>{{SimplifiedColored}}&nbsp<br></div>
<div class=pinyin>{{Pinyin}}&nbsp<br></div>
<div class=meaning>{{MeaningES}} <span class=en-secondary>({{Meaning}})</span>&nbsp<br></div>
<div style="line-height:50%;"><br></div>

<hr>

<div id="hanziAnswerBox" data-word="{{Simplified}}" style="display:flex; overflow-x:auto; border:2px solid #999; background:#fff; margin:10px auto 0 auto; width:fit-content; max-width:100%;"></div>

<script>
function _hanziAnswerInit() {
    var container = document.getElementById('hanziAnswerBox');
    if (!container) return;
    var word = container.getAttribute('data-word');
    var chars = Array.from(word);
    var cellSize = 170;

    function loader(char, onLoad, onError) {
        var data = (typeof HANZI_DATA !== 'undefined') ? HANZI_DATA[char] : null;
        if (data) {
            onLoad(data);
        } else if (onError) {
            onError('missing data for ' + char);
        }
    }

    var writers = chars.map(function (char, i) {
        var cell = document.createElement('div');
        cell.id = 'hanziAnswerCell' + i;
        cell.style.width = cellSize + 'px';
        cell.style.height = cellSize + 'px';
        cell.style.flex = '0 0 auto';
        if (i > 0) cell.style.borderLeft = '1px dashed #ccc';
        container.appendChild(cell);

        return HanziWriter.create(cell.id, char, {
            width: cellSize,
            height: cellSize,
            padding: 5,
            showCharacter: false,
            charDataLoader: loader,
        });
    });

    // Animate one character at a time (not all at once), left to right.
    function animateNext(i) {
        if (i >= writers.length) return;
        writers[i].animateCharacter({
            onComplete: function () {
                animateNext(i + 1);
            },
        });
    }
    animateNext(0);
}
if (document.readyState === 'complete') {
    _hanziAnswerInit();
} else {
    window.addEventListener('load', _hanziAnswerInit);
}
</script>

<div style="line-height:70%;"><br></div>

<hr>

<div class=synonyms>{{SynonymsES}}</div>
<div class=synonymsColored>{{SynonymsColored}}</div>
<div class=en-secondary>{{Synonyms}}</div>

<hr>

<div class=dictionary>{{DictionarySimplified}}&nbsp<br></div>
<div class=dictionaryColored>{{DictionarySimplifiedColored}}&nbsp<br></div>
<div style="line-height:20%;"><br></div>
<div class=dictionaryMeaning>{{DictionaryMeaningES}} <span class=en-secondary>({{DictionaryMeaning}})</span>&nbsp<br></div>
<div style="line-height:70%;"><br></div>

<hr>

<div class=sentence>{{SentenceSimplified}}&nbsp<br></div>
<div class=sentenceColored>{{SentenceSimplifiedColored}}&nbsp<br></div>
<div style="line-height:20%;"><br></div>
<div class=sentenceMeaning>{{SentenceMeaningES}} <span class=en-secondary>({{SentenceMeaning}})</span>&nbsp<br></div>
<div style="line-height:70%;"><br></div>

<!-- Pleco lookup buttons, disabled by default: they only work if the Pleco
     Chinese dictionary app is installed on the device. Uncomment to re-enable.
<div class=bottomcontrols>
    <div class=controlPleco><a href="plecoapi://x-callback-url/s?q={{Simplified}}&mode=df&hw={{Simplified}}&py={{Pinyin}}&sec=dict&x-source=AnkiDroid">&nbsp&nbspWord&nbsp</a></div>
    <div class=controlPleco><a href="plecoapi://x-callback-url/s?q={{SentenceSimplified}}">&nbspSentence</a></div>
</div>
-->
"""


def _discover_input_tsvs() -> List[Path]:
    """Every data/<level>/input.tsv found on disk, e.g. data/hsk1/input.tsv."""
    return sorted(DATA_DIR.glob("*/input.tsv"))


def _used_characters(input_tsvs: List[Path]) -> set:
    chars = set()
    for tsv in input_tsvs:
        df = pd.read_csv(tsv, sep="\t", dtype=str)
        for word in df["Simplified"].dropna():
            chars.update(word)
    return chars


def build(input_tsvs: Optional[List[Path]] = None) -> None:
    if input_tsvs is None:
        input_tsvs = _discover_input_tsvs()
        if not input_tsvs:
            raise SystemExit(f"No input.tsv files found under {DATA_DIR}/*/input.tsv")

    lib_js = (HANZI_DIR / "hanzi-writer.min.js").read_text(encoding="utf-8")
    lib_js = "\n".join(
        line for line in lib_js.splitlines() if not line.strip().startswith("//# sourceMappingURL")
    )

    data_dir = HANZI_DIR / "data"
    used_chars = _used_characters(input_tsvs)
    combined = {}
    missing = []
    for char in sorted(used_chars):
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

    header = f"<script>\n{lib_js}\n</script>\n\n<script>\n{data_blob}\n</script>\n\n"

    (HANZI_DIR / "front.html").write_text(header + FRONT_BODY, encoding="utf-8")
    (HANZI_DIR / "back.html").write_text(header + BACK_BODY, encoding="utf-8")
    print(f"Embedded {len(combined):,} characters (from {len(input_tsvs)} word list(s)) into front.html and back.html")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenerate card_template/hanzi_writing/{front,back}.html.",
    )
    parser.add_argument(
        "-i", "--input", type=Path, nargs="*", default=None, metavar="INPUT.tsv",
        help="One or more word-list TSVs to scan for characters. Default: every data/*/input.tsv (all HSK levels).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    build(args.input)


if __name__ == "__main__":
    main()
