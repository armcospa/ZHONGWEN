# Guía para desarrollar y ampliar el proyecto

Esta guía es para quien quiera regenerar los mazos, añadir vocabulario o niveles, cambiar el diseño de las tarjetas o adaptar el proyecto a otro idioma. Para estudiar con los mazos ya generados basta con el [README](README.md).

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate       # Windows; en macOS/Linux: source .venv/bin/activate
pip install -e ".[deck,test]"
pytest
```

## Estructura del repositorio

```
src/zhongwen_anki/
├── enrich.py          # zhongwen-anki: input.tsv -> output.tsv
├── build_deck.py      # zhongwen-anki-build-deck: output.tsv -> .apkg
├── build_all.py       # zhongwen-anki-build-all: todos los niveles de una vez
├── hanzi_writer.py    # bloque HanziWriter + datos de trazos, generado en memoria
├── utilities.py       # segmentación (jieba), pinyin (pypinyin) y coloreado por tono
├── export_stats.py    # zhongwen-anki-export-stats
└── wip/analyze_stats.py   # zhongwen-anki-analyze-stats (en desarrollo)
card_template/
├── <código>/front.html, back.html   # una carpeta por tipo de tarjeta
├── _shared/                         # bloques comunes que se incluyen en las plantillas
├── hanzi_writer/                    # HanziWriter + datos de trazos por carácter (fuente)
└── styling.css
data/hskN/input.tsv     # vocabulario de cada nivel (fuente de verdad)
data/hskN/output.tsv    # generado, ignorado por git
decks/HSKN.apkg         # mazos publicados
docs/                   # documentación ampliada y especificación de tarjetas
tests/
```

## Pipeline

```
data/hskN/input.tsv --zhongwen-anki--> data/hskN/output.tsv --zhongwen-anki-build-deck--> decks/HSKN.apkg
```

1. **`enrich.py`** valida las columnas obligatorias, elimina las filas duplicadas (misma clave `Simplified + Pinyin + Meaning`), colorea los caracteres por tono y genera el pinyin de la frase de ejemplo y de la definición.
2. **`build_deck.py`** monta el tipo de nota (campos, las 10 plantillas y el CSS), crea una nota por fila con su GUID, rellena `SourceLevel` con el nivel y escribe el `.apkg` comprimido.

`zhongwen-anki-build-all` hace los dos pasos para todos los niveles que encuentre en `data/*/input.tsv`. **Usa siempre este comando antes de publicar**: el tipo de nota es único y compartido por todos los niveles, así que un mazo generado con plantillas antiguas sobrescribiría el tipo de nota de los demás al importarlo. `tests/test_decks.py` falla si algún `decks/*.apkg` no coincide con las plantillas y los datos actuales.

## Plantillas de tarjeta

La especificación funcional (qué muestra y qué pide cada tarjeta) está en [`docs/templates/README.md`](docs/templates/README.md).

- Cada tipo de tarjeta tiene su carpeta en `card_template/` con `front.html` y `back.html`. La lista ordenada de tipos está en `TEMPLATES` (`build_deck.py`).
- **Solo se añaden tipos al final de `TEMPLATES`.** Anki identifica las tarjetas de una nota por su posición (`ord`): reordenar o insertar en medio haría que el historial de una tarjeta pasara a otra. Al añadir uno, actualiza también `CARD_TYPE_BY_ORD` (`export_stats.py`), `CARD_TYPE_DESCRIPTIONS` (`wip/analyze_stats.py`), `EXPECTED_TEMPLATE_NAMES` (`tests/test_build_deck.py`) y la documentación.
- Los bloques repetidos viven en `card_template/_shared/` y se incluyen con un comentario `<!-- include: nombre -->`, que `build_deck.py` sustituye al empaquetar:

| Include | Contenido |
|---|---|
| `level_badge` | Nivel de la palabra (campo `SourceLevel`) en la esquina superior izquierda. El CSS lo oculta para HSK1. |
| `details` | Sinónimos (solo si hay), definición y frase de ejemplo |
| `reveal_controls` | Botón **Unhide** y su script. Obligatorio en cualquier plantilla que use clases ocultas (`*PinyinHidden`, `*Colored`). |
| `hanzi_quiz` | Caja para dibujar el hanzi con HanziWriter (anversos de `PM2H`, `M2H` y `P2H`) |
| `hanzi_answer` | Animación del hanzi correcto (reversos de esas tres tarjetas) |
| `hanzi_writer` | Generado en memoria por `hanzi_writer.py`: la librería HanziWriter y los datos de trazos de todos los caracteres de todos los niveles |
| `pinyin_hint` | Pista en la caja de texto del anverso de `H2P`, `M2P` y `HM2P` (`àihào / ai4hao4`) |
| `pinyin_check` | Recorrige en el reverso la respuesta de `{{type:Pinyin}}`: acepta tildes o números, ignora mayúsculas, espacios y apóstrofos, y muestra la solución en el formato que más usó el estudiante. Lee lo escrito de la comparación de Anki (`#typeans`) y, si no la encuentra, deja la de Anki. Contiene la lista de sílabas válidas del pinyin, que `tests/test_pinyin_check.py` compara con la de Python. |

- HanziWriter y los datos de trazos van incrustados en la plantilla, no como ficheros multimedia, porque el webview de Anki (sobre todo AnkiDroid) no siempre carga a tiempo los recursos externos. Ver [`card_template/hanzi_writer/NOTICE.md`](card_template/hanzi_writer/NOTICE.md).
- Los textos `{{CampoES}}` se reescriben a `{{CampoXX}}` cuando se construye con `--target-lang XX`.
- Las fuentes se definen como variables CSS al principio de `styling.css` (`--font-kai`, `--font-song`, `--font-pinyin`, `--font-latin`, `--font-ui`): cada una es una lista con la fuente original de Windows y sus equivalentes en macOS/iOS, Linux y Android, terminada en una familia genérica.
- El campo `PinyinNumbered` (`ai4hao4`, tono neutro `5`) lo calcula `utilities.pinyin_to_numbered` a partir de `Pinyin`, segmentando en sílabas válidas.
- Los tests comprueban, entre otras cosas, que no quedan includes sin resolver, que no hay dos anversos iguales, que todo contenido oculto tiene botón **Unhide**, que todas las respuestas muestran el nivel y que los titulares usan el simplificado.

Para ver una tarjeta sin abrir Anki, se puede leer el modelo de un `.apkg` (tabla `col.models`), sustituir los campos de una nota y abrir el HTML en un navegador. Los anversos con `{{type:Pinyin}}` necesitan un `<input>` en su lugar.

## Cambios en el tipo de nota (campos y tipos de tarjeta)

Todos los niveles comparten un tipo de nota (`Chino - HSK (ES/EN)`, `MODEL_ID` en `build_deck.py`). Al importar un `.apkg`, Anki busca en la colección un tipo de nota con ese mismo ID:

- **Si la estructura es la misma** (mismos campos y mismos tipos de tarjeta), actualiza el HTML y el CSS de las plantillas y el contenido de las notas. No hay que hacer nada especial.
- **Si la estructura cambia** (se añaden, quitan o reordenan campos o tipos de tarjeta), Anki no puede aplicarla a las notas que ya existen sin modificar la estructura de la colección. Por defecto, crea un tipo de nota nuevo con un sufijo y deja las notas antiguas sin actualizar. Con la opción **Merge note types** del diálogo de importación (Anki 23.10 o posterior), fusiona la estructura nueva con la existente. Como eso altera el esquema de la colección, la siguiente sincronización con AnkiWeb es completa (*one-way sync*).

Ya ocurría antes de la versión 0.4.0, aunque no estaba documentado: cada tipo de tarjeta añadido (`Pinyin -> Significado`, `Significado -> Pinyin`) y el campo `SourceLevel` de HSK4 cambiaron la estructura. Por eso los mazos publicados hasta entonces tenían versiones distintas del tipo de nota (HSK1 con 6 tipos de tarjeta y 21 campos, HSK2–3 con 5, HSK4 con 6 y 22), y combinarlos en una colección requería fusionar o creaba copias.

Reglas para cambiar la estructura:

- **Solo se añade al final**, tanto en `TEMPLATES` (`build_deck.py`) como en `output_columns` (`enrich.py`). No se quitan ni se reordenan campos o tipos de tarjeta: las tarjetas guardan su historial por posición, y una fusión con elementos desplazados podría asignarlos mal.
- **Agrupa los cambios de estructura** en una misma versión, para que los usuarios fusionen y hagan la sincronización completa una sola vez.
- **Avísalo en el README** (sección *Actualizar un mazo ya importado*) indicando qué cambia.
- **Pruébalo antes en un perfil de Anki aparte**: importa la versión publicada, estudia unas tarjetas, importa la nueva con *Merge note types* y comprueba que no hay notas duplicadas ni un segundo tipo de nota, que los campos de una nota conservan su contenido y que el historial de las tarjetas estudiadas sigue ahí.

## GUID: identificador estable de cada palabra

Anki reconoce que una nota importada ya existe por su **GUID**, un identificador corto que acompaña a cada nota. Si al reimportar un `.apkg` el GUID coincide, Anki actualiza el contenido y conserva el progreso. Si no coincide, crea una nota nueva: la palabra aparece duplicada y el historial se queda en la antigua.

genanki calcula por defecto el GUID a partir de **todos** los campos de la nota, así que cualquier cambio (corregir una errata, añadir una columna...) generaría un GUID distinto. Para evitarlo, el GUID de cada palabra está congelado en la columna `Guid` de `data/hskN/input.tsv`:

- **No edites ni borres la columna `Guid`.** Las palabras ya publicadas conservan su GUID aunque cambie su contenido.
- Las filas nuevas pueden dejarla vacía: `build_deck.note_guid` deriva entonces uno de `Simplified + Pinyin + Meaning`, que no cambia aunque edites la frase, los sinónimos, etc. Para que tampoco cambie si corriges el significado, congélalo tras publicar:

```python
import pandas as pd
from zhongwen_anki.build_deck import note_guid

path = "data/hsk5/input.tsv"
df = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
if "Guid" not in df:
    df["Guid"] = ""
df["Guid"] = [note_guid(r.Simplified, r.Pinyin, r.Meaning, r.Guid) for r in df.itertuples()]
df.to_csv(path, sep="\t", index=False)
```

## Añadir vocabulario o un nivel nuevo

1. Prepara la lista de palabras del nivel (por ejemplo, la lista oficial del HSK 3.0).
2. Genera el `input.tsv` con un LLM usando el prompt de abajo y guárdalo en `data/hskN/input.tsv`. Revisa el resultado: pinyin, significados y, sobre todo, que haya sinónimos (en HSK3 el LLM los dejó casi todos vacíos).
3. Si el nivel es nuevo, añade un ID estable para él en `DECK_IDS` (`build_deck.py`). No cambies nunca el ID de un nivel ya publicado: Anki identifica los mazos por ese ID.
4. Si hay caracteres sin datos de trazos, el paso siguiente falla y los enumera. Descárgalos con `npm install hanzi-writer-data` y copia los `<carácter>.json` de `node_modules/hanzi-writer-data/` a `card_template/hanzi_writer/data/`.
5. Ejecuta `zhongwen-anki-build-all`, comprueba que `pytest` pasa y escribe un `data/hskN/README.md` como el de los demás niveles.

Para palabras con varias acepciones con la misma lectura (生 *shēng*: «dar a luz» / «crudo»), usa una fila por acepción. Solo se consideran duplicadas las filas con el mismo `Simplified`, `Pinyin` **y** `Meaning`.

### Prompt para el LLM

Sustituye `<IDIOMA_DESTINO>` por tu idioma (las plantillas de este repositorio están pensadas para **español**, sufijo `ES`) y añade la lista de palabras al final.

~~~text
### Prompt:

Crea una tabla separada por tabulaciones para la siguiente lista de palabras chinas. Cada entrada debe incluir las siguientes columnas:

1.  **Simplified**: caracteres simplificados.
2.  **Traditional**: caracteres tradicionales.
3.  **Pinyin**: pinyin con tonos, con **un espacio** entre sílabas de palabras distintas.
4.  **Meaning**: significado en inglés.
5.  **Meaning<IDIOMA_DESTINO>**: significado en <IDIOMA_DESTINO>, traducido directamente del chino (no del inglés de la columna anterior), para poder comparar ambas traducciones de forma independiente.
6.  **SentenceSimplified**: frase de ejemplo sencilla en chino que dé buen contexto a la palabra (importante si el carácter es polifónico).
7.  **SentenceMeaning**: traducción al inglés de la frase de ejemplo.
8.  **SentenceMeaning<IDIOMA_DESTINO>**: traducción al <IDIOMA_DESTINO> de la frase de ejemplo, también directamente del chino.
9.  **Synonyms**: hasta 3 sinónimos en inglés, formato "CaracteresSimplificados (Pinyin) - Traducción", separados por `<br>`.
10. **Synonyms<IDIOMA_DESTINO>**: los mismos sinónimos, con la traducción en <IDIOMA_DESTINO>.
11. **DictionarySimplified**: definición corta en chino.
12. **DictionaryMeaning**: traducción al inglés de esa definición.
13. **DictionaryMeaning<IDIOMA_DESTINO>**: traducción al <IDIOMA_DESTINO> de esa definición, directamente del chino.

Procesa tantas palabras como sea posible en orden; si no puedes terminar la lista completa en una respuesta, yo enviaré "continua" para que sigas desde donde lo dejaste.
Si una palabra tiene un error (caracteres mal formados, pinyin mal escrito, etc.), corrígelo e indica la corrección al final.
Si una palabra es demasiado ambigua para interpretarla con confianza, no la incluyas en la tabla y lístala al final indicando que no se pudo determinar su significado.
Si una palabra tiene varios significados comunes con la misma lectura y el nivel los incluye por separado, crea una fila por significado; si no, elige el más general según el uso habitual.

Responde en un bloque de código TSV, sin generar código como tal, sin usar Python ni pandas.

-----

### Lista de palabras

<<LISTA DE PALABRAS AQUÍ>>
~~~

[`data/hsk1/input.tsv`](data/hsk1/input.tsv) es un ejemplo real del resultado.

## Otro idioma de destino

El idioma no está fijado en el código: es el sufijo de las columnas de traducción. Con `--target-lang FR`, `zhongwen-anki` lee `MeaningFR`, `SentenceMeaningFR`, `SynonymsFR` y `DictionaryMeaningFR`, y `zhongwen-anki-build-deck` (o `build-all`) reescribe las plantillas para usar esos campos. Los textos fijos de las plantillas («Dibuja cada trazo con el ratón o el dedo.», el contador de caracteres de `_shared/hanzi_quiz.html`, `繁`, `Unhide`) están en español y hay que traducirlos a mano.

Para añadir esas columnas a los `input.tsv` existentes, lo más práctico es traducir las columnas en inglés con un LLM, por partes si el fichero es largo. Un prompt posible (sustituye `<LANG>` y `<SUFIJO>`):

~~~text
Below is a tab-separated table of Chinese vocabulary. For each row, translate the English columns into <LANG> and return a tab-separated table with exactly these columns, in this order and with this header:
Simplified	Meaning<SUFIJO>	SentenceMeaning<SUFIJO>	Synonyms<SUFIJO>	DictionaryMeaning<SUFIJO>

- Meaning<SUFIJO>: translation of Meaning (use the Chinese word and example sentence to pick the right sense).
- SentenceMeaning<SUFIJO>: translation of SentenceMeaning.
- Synonyms<SUFIJO>: Synonyms with only the translation after " - " replaced; keep the Chinese characters, the pinyin in parentheses and the <br> separators exactly as they are. Leave it empty if Synonyms is empty.
- DictionaryMeaning<SUFIJO>: translation of DictionaryMeaning.
Keep one output row per input row, in the same order. Answer only with the table in a code block.

<paste the Simplified, SentenceSimplified, Meaning, SentenceMeaning, Synonyms and DictionaryMeaning columns here>
~~~

Después, une las columnas al `input.tsv` por la columna `Simplified` y en el mismo orden (hay palabras con varias filas, como 生), y genera con `zhongwen-anki-build-all --target-lang <SUFIJO>`.

## Comprobaciones antes de publicar

- `zhongwen-anki-build-all` sin errores.
- `pytest` en verde. Lo ejecuta también el CI de GitHub (`.github/workflows/tests.yml`) en cada push y pull request. Incluye `tests/test_decks.py`, que compara los mazos publicados con las fuentes y comprueba que ningún nivel repite palabras de uno anterior, y `tests/test_pinyin_check.py`, que ejecuta con Node la corrección del pinyin de las tarjetas (se salta si Node no está instalado).
- Si cambia la estructura del tipo de nota, sigue las reglas de [Cambios en el tipo de nota](#cambios-en-el-tipo-de-nota-campos-y-tipos-de-tarjeta).

## Material local

`docs/local/` está ignorada por git: guarda allí lo que no se publica (listados imprimibles, PDFs de referencia, notas de trabajo futuro).
