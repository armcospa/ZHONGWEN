# HSK2 — vocabulario pendiente

Esta carpeta está preparada para el vocabulario de HSK2, pero todavía no
contiene ningún `input.tsv`. Para completarla:

1. Consigue la lista oficial de vocabulario de HSK2 (estándar 3.0).
2. Genera un `input.tsv` con el mismo esquema que
   [`data/hsk1/input.tsv`](../hsk1/input.tsv) (cabecera obligatoria:
   `Simplified`, `Traditional`, `Pinyin`, `Meaning`, `SentenceSimplified`,
   `SentenceMeaning`, `Synonyms`, `DictionarySimplified`,
   `DictionaryMeaning`; columnas de traducción opcionales, p. ej. `MeaningES`
   — ver el prompt de LLM en el [`README.md`](../../README.md) principal).
3. Ejecuta:
   ```bash
   zhongwen-anki-build-hanzi-templates          # añade los caracteres nuevos de HSK2
   zhongwen-anki -i data/hsk2/input.tsv -o data/hsk2/output.tsv
   zhongwen-anki-build-deck -i data/hsk2/output.tsv -o decks/HSK2.apkg --level HSK2
   ```

`HSK2` ya tiene un ID de mazo reservado en `DECK_IDS` (`src/zhongwen_anki/build_deck.py`),
así que no hace falta tocar código para generar este nivel.
