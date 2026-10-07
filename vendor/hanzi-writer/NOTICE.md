# Third-party assets used by the hanzi-writing cards (PM2H, M2H, P2H)

- `hanzi-writer.min.js` — [HanziWriter](https://www.npmjs.com/package/hanzi-writer), MIT license.
- `data/*.json` — one stroke-data file per Chinese character, from
  [hanzi-writer-data](https://www.npmjs.com/package/hanzi-writer-data)
  (itself derived from the [Make Me a Hanzi](https://github.com/skishore/makemeahanzi)
  project / Arphic PL fonts), distributed under the Arphic Public License.

These files are the *source* that `zhongwen_anki/hanzi_writer.py` inlines into
the card templates when a deck is built (wherever a template contains
`<!-- include: hanzi_writer -->`). The library source and every character's
stroke data end up embedded directly as static content — no `<script src>`,
no `fetch()`, no Anki media files — because Anki's webview has a known race
condition where external script/media files aren't always loaded in time
when a card's own inline script runs (worse on AnkiDroid). The card scripts
also defer initialization to the `window.load` event as an extra safeguard,
following the pattern used by
[krmanik/Anki-xiehanzi](https://github.com/krmanik/Anki-xiehanzi) — an
actively maintained HanziWriter+Anki deck confirmed to work across Anki
Desktop, AnkiDroid and AnkiMobile.

When new vocabulary introduces characters without stroke data, building the
deck fails and lists them. Get them with `npm install hanzi-writer-data` and
copy the needed `<char>.json` files from `node_modules/hanzi-writer-data/`
into `data/`.
