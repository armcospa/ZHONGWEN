# Third-party assets used by the "Escribir Hanzi" card

- `hanzi-writer.min.js` — [HanziWriter](https://www.npmjs.com/package/hanzi-writer), MIT license.
- `data/*.json` — one stroke-data file per Chinese character, from
  [hanzi-writer-data](https://www.npmjs.com/package/hanzi-writer-data)
  (itself derived from the [Make Me a Hanzi](https://github.com/skishore/makemeahanzi)
  project / Arphic PL fonts), distributed under the Arphic Public License.

Both are kept on disk only as the *source* used to regenerate `front.html`
and `back.html` (run `python -m zhongwen_anki.build_hanzi_templates` after
changing either). Those two generated files embed the library source and
every character's stroke data directly as static content — no `<script src>`,
no `fetch()`, no Anki media files — because Anki's webview has a known race
condition where external script/media files aren't always loaded in time
when a card's own inline script runs (worse on AnkiDroid). The generated
templates also defer initialization to the `window.load` event as an extra
safeguard, following the pattern used by
[krmanik/Anki-xiehanzi](https://github.com/krmanik/Anki-xiehanzi) — an
actively maintained HanziWriter+Anki deck confirmed to work across Anki
Desktop, AnkiDroid and AnkiMobile.

Regenerate `data/*.json` with `npm install hanzi-writer hanzi-writer-data`
and copy the needed `<char>.json` files from `node_modules/hanzi-writer-data/`
(e.g. after adding HSK2 vocabulary introduces new characters), then re-run
`build_hanzi_templates`.
