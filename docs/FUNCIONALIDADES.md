# Funcionalidades, posibilidades y mejoras futuras

Este documento resume todo lo que se ha construido sobre el repositorio original
`zhongwen-anki` para estudiar el vocabulario obligatorio de **HSK (estándar 3.0,
vigente desde julio de 2026)**, qué hace cada pieza, qué puertas abre, y qué se
podría mejorar más adelante. El pipeline es el mismo para cualquier nivel
(HSK1, HSK2, HSK3...); por ahora solo **HSK1 (301 palabras)** tiene el
vocabulario ya completo en `data/hsk1/`.

## 1. Qué hay implementado

### 1.1 Generación del vocabulario (`data/<nivel>/input.tsv`)
- Cada nivel vive en su propia carpeta: `data/hsk1/input.tsv` (301 palabras
  oficiales de HSK1 3.0 (2026), extraídas del PDF de Khanji School /
  Chinesimple y verificadas una por una), `data/hsk2/`, `data/hsk3/` (listas
  para rellenar con el mismo esquema — ver el `README.md` de cada carpeta).
- Por cada palabra: carácter simplificado, tradicional, pinyin con tonos,
  significado, frase de ejemplo, hasta 3 sinónimos y una definición corta —
  **todo en inglés y en el idioma de destino elegido por separado** (columnas
  `Meaning`/`MeaningES`, `SentenceMeaning`/`SentenceMeaningES`,
  `Synonyms`/`SynonymsES`, `DictionaryMeaning`/`DictionaryMeaningES` — el
  sufijo `ES` es el idioma de destino por defecto, configurable con
  `--target-lang`, ver 1.2).
- Las traducciones se hicieron directamente desde el chino (no traduciendo el
  inglés ya existente), precisamente para evitar el efecto "teléfono roto" de
  una doble traducción y poder comparar ambas.

### 1.2 Procesado (`zhongwen_anki`)
- `zhongwen-anki -i data/hsk1/input.tsv -o data/hsk1/output.tsv`: colorea los
  caracteres por tono, genera el pinyin de las frases y definiciones
  automáticamente (vía `jieba` + `pypinyin`), y produce el TSV final listo
  para Anki.
- `--target-lang LANG` (por defecto `ES`): el idioma de destino no está fijado
  a español en el código — es un sufijo de columna configurable. Para
  preparar un mazo en otro idioma nativo (p. ej. francés), el TSV de entrada
  necesita columnas `MeaningFR`, `SentenceMeaningFR`, etc. en vez de `...ES`,
  y se ejecuta con `--target-lang FR`.
- `zhongwen-anki-build-deck -i data/hsk1/output.tsv -o decks/HSK1.apkg --level HSK1`:
  empaqueta ese TSV en un `.apkg` completo (tipo de nota + plantillas + CSS +
  multimedia) para el nivel indicado, listo para importar sin tocar nada a
  mano en Anki. `--level` controla el nombre del mazo y la etiqueta de cada
  nota; `--target-lang` (debe coincidir con el usado en el paso anterior)
  hace que las plantillas HTML referencien los campos del idioma correcto.
- `zhongwen-anki-build-hanzi-templates`: regenera las plantillas de "Escribir
  Hanzi" escaneando **todos** los `data/<nivel>/input.tsv` que encuentre — el
  tipo de nota es el mismo para todos los niveles, así que sus datos de
  trazos se combinan en una sola pasada.
- `zhongwen-anki-export-stats`: exporta el historial de repasos de Anki
  (`collection.anki2` → `revlog`) a un CSV limpio para analizarlo fuera de Anki.
- Todo corre en un entorno virtual local (`.venv/`), sin tocar el Python
  global. Instalación: `pip install -e ".[deck,test]"`.

### 1.3 Tipo de nota "Chino - HSK (ES/EN)" — 5 tarjetas por palabra

El tipo de nota es **uno solo, compartido por todos los niveles** (HSK1,
HSK2, HSK3...); lo que distingue a cada nivel es el mazo (`Chino - HSK1
(HSK 3.0)`, `Chino - HSK2 (HSK 3.0)`...) y la etiqueta (`HSK1`, `HSK2`...)
de cada nota, ambos asignados por `zhongwen-anki-build-deck --level`.
| Tarjeta | Pregunta | Respuesta | Qué entrena |
|---|---|---|---|
| Hanzi → Significado | Carácter | Significado (ES, con EN de apoyo) | Lectura |
| Significado → Hanzi | Significado (ES, con EN de apoyo) | Carácter + pinyin | Producción |
| Pinyin → Significado | Pinyin con tonos (carácter oculto) | Carácter + significado | Reconocer la palabra solo por su pinyin, sin ver el hanzi |
| Escribir Pinyin | Carácter | Escribes el pinyin con tonos, Anki compara letra a letra | Ortografía del pinyin |
| Escribir Hanzi | Pinyin + significado | Dibujas el carácter trazo a trazo, evaluado automáticamente | Escritura |

`Pinyin -> Significado` es la plantilla más nueva (`card_template/pinyin_to_meaning/`,
`ord=4` en `build_deck.build_model` -- añadida al *final* de la lista de
plantillas a propósito, para no reordenar los `ord` 0-3 ya existentes y no
romper el progreso/historial de tarjetas ya importadas).

La tarjeta de escritura de hanzi usa **[HanziWriter](https://hanziwriter.org/)**
(librería JS de código abierto) con los datos de trazos oficiales de cada uno
de los 248 caracteres únicos usados en HSK1. Tanto la librería como los datos
de trazos van **incrustados directamente como texto estático** dentro de
`front.html`/`back.html` (nada de `<script src>` externo, ni `fetch()`, ni
ficheros multimedia en el `.apkg`) — Anki tiene una condición de carrera
conocida donde los recursos externos no siempre están listos a tiempo cuando
se ejecuta el script de la tarjeta, sobre todo en AnkiDroid. Todas las
palabras de una misma tarjeta se dibujan dentro de **una sola caja** (con
scroll horizontal si la palabra tiene varios caracteres), no una caja por
carácter. No es una comparación "a ojo": HanziWriter valida forma, dirección
y orden de cada trazo. Diseño verificado contra
[krmanik/Anki-xiehanzi](https://github.com/krmanik/Anki-xiehanzi), un mazo
HanziWriter+Anki mantenido activamente que funciona en Desktop, AnkiDroid y
AnkiMobile.

### 1.4 Organización del estudio
- Un mazo por nivel (`Chino - HSK1 (HSK 3.0)`, `Chino - HSK2 (HSK 3.0)`...),
  pero **un solo tipo de nota** compartido: así todos los niveles tienen la
  misma estructura de tarjetas y solo hay una fuente de verdad por palabra.
- Para sesiones centradas en una sola habilidad (p. ej. solo pinyin antes de
  un examen), se usan **mazos filtrados** (`Tools → Create Filtered Deck`,
  búsqueda `card:"Escribir Pinyin"`) — sin duplicar datos ni progreso. Puedes
  combinar varios niveles a la vez: `deck:"Chino - HSK*" card:"Escribir Pinyin"`.
- Sincronización Anki Desktop ↔ AnkiWeb ↔ AnkiDroid con una sola cuenta.

## 2. Qué posibilidades abre esto

- **Escalar a otros niveles (ya implementado)**: el pipeline entero
  (`data/<nivel>/input.tsv` → `zhongwen-anki` → `build-deck --level`) es
  genérico; añadir HSK2 o HSK3 es cuestión de rellenar
  `data/hsk2/input.tsv`/`data/hsk3/input.tsv` con el mismo esquema que
  `data/hsk1/input.tsv` y volver a ejecutar
  `zhongwen-anki-build-hanzi-templates` (añade los caracteres nuevos) y
  `zhongwen-anki-build-deck --level HSK2`. Para HSK4-6 hace falta además
  añadir una entrada en `DECK_IDS` dentro de `build_deck.py`.
- **Análisis de tu propio aprendizaje**: con `export_stats.py` tienes acceso
  a cada repaso individual (acierto/fallo, tiempo empleado, facilidad,
  intervalo). Se puede usar para ver qué palabras cuestan más, cómo evoluciona
  tu ritmo de aciertos, o comparar las 5 tarjetas entre sí (¿fallas más en
  pinyin que en escritura?).
- **Practicar habilidades por separado sin perder el hilo**: mazos filtrados
  por tipo de tarjeta, por etiqueta (`tag:HSK1`), o por "leeches" (palabras
  que fallas repetidamente — Anki las etiqueta solas).
- **Base reutilizable para cualquier idioma con escritura no latina**: el
  patrón (TSV → plantillas EN/ES → HanziWriter para trazos) es extensible a
  otros alfabetos/silabarios si en el futuro te interesa (p. ej. kana
  japonés, aunque HanziWriter es específico de hanzi/kanji).

## 3. Guía rápida de uso en Anki

### 3.1 Crear un mazo filtrado

1. En Anki Desktop: **Tools → Create Filtered Deck** (o `Herramientas → Crear mazo filtrado`).
2. Ponle un nombre, por ejemplo `Repaso Pinyin`.
3. En **Search**, escribe:
   ```
   deck:"Chino - HSK1 (HSK 3.0)" card:"Escribir Pinyin"
   ```
4. Ajusta el límite de tarjetas si quieres (por defecto coge todas las que tocan repasar).
5. **Build**. Se crea un mazo temporal con solo esas tarjetas, sin duplicar nada — tu progreso real sigue en el mazo original y al vaciar el filtrado (`Empty`) las tarjetas vuelven a su sitio.

Puedes hacer lo mismo con `card:"Hanzi -> Significado"`, `card:"Significado -> Hanzi"`, `card:"Pinyin -> Significado"` o `card:"Escribir Hanzi"` para las otras cuatro.

**Solución de problemas — "No se encontraron tarjetas coincidentes":**
- Lo más probable es que tu colección de Anki todavía no tenga importada la versión del mazo que incluye esa plantilla en concreto (p. ej. "Escribir Pinyin" y "Escribir Hanzi" se añadieron en pasos posteriores del proyecto) — reimporta el `.apkg` más reciente de [`decks/`](../decks/) primero.
- Comprueba el nombre exacto del mazo y de la plantilla desde **Browse**: en la barra lateral izquierda, despliega "Decks" y "Card Types" y haz clic en el que quieras — Anki rellena la búsqueda automáticamente con la sintaxis correcta (evita errores de tildes, mayúsculas o el guion de "Escribir Pinyin").
- Si tienes cartas suspendidas o ya en otro mazo filtrado, no aparecerán salvo que añadas `is:suspended` o quites el filtro que las excluye (el propio mensaje de error de Anki te avisa de esto).

### 3.2 Que las tarjetas nuevas salgan barajadas, no alfabéticas

Esto pasa porque el orden por defecto es "orden de inserción", y como el TSV está ordenado más o menos alfabéticamente por pinyin, las primeras palabras que tocan son todas con "a". Se arregla en las opciones del mazo:

1. Clic en el engranaje ⚙️ junto al mazo → **Options**.
2. En la sección **New Cards** (o "Tarjetas nuevas"), busca **"New card gather order"** (orden de recogida de tarjetas nuevas) → cámbialo a **"Random order"** (orden aleatorio) en vez de "Deck order"/"Ascending position".
3. Guarda.

Esto afecta a las tarjetas que **aún no se han visto**. Las que ya han salido no se reordenan solas, pero como son pocas no importa. Si quieres forzar que se reordenen ya mismo:
- **Browse** → selecciona todas las tarjetas nuevas del mazo → clic derecho → **Reposition new cards** → marca "Shuffle order" (barajar).

### 3.3 Borrar historial y empezar de cero

- **Browse** (`Explorar`) → busca `deck:"Chino - HSK1 (HSK 3.0)"` → selecciona todas (Ctrl+A) → clic derecho → **Forget** (`Olvidar`).
- Esto resetea las tarjetas a estado "nueva" y **también borra su historial de repasos de las estadísticas** (no solo el progreso de repetición espaciada). Es lo que buscas para "empezar de cero".
- Ojo: esto **no se puede deshacer fácilmente** una vez sincronizado con AnkiWeb en ambos dispositivos, así que si tienes dudas, exporta antes una copia (`File → Export → Anki Deck Package`, incluyendo el planning de scheduling) por si acaso.

### 3.4 Descargar las estadísticas para procesarlas tú

Anki no tiene un botón nativo de "exportar CSV" en la pantalla de Stats, pero **toda tu actividad está en una base de datos SQLite** que puedes abrir con Python, Excel (vía ODBC) o cualquier herramienta que hable SQLite:

1. Cierra Anki (o al menos sincronízalo antes, para que el fichero local esté al día).
2. Localiza el archivo de tu perfil (en Windows):
   ```
   %APPDATA%\Anki2\<Nombre de tu perfil>\collection.anki2
   ```
3. Ábrelo con cualquier herramienta SQLite, o en Python:
   ```python
   import sqlite3, pandas as pd
   con = sqlite3.connect("collection.anki2")
   revlog = pd.read_sql("SELECT * FROM revlog", con)
   revlog.to_csv("mis_repasos.csv", index=False)
   ```
   La tabla `revlog` tiene **una fila por cada repaso que has hecho** (timestamp, si acertaste/fallaste, tiempo empleado, intervalo, etc.) — es la fuente de datos más completa que hay, mejor que cualquier export de la interfaz.
4. Alternativa ya hecha en este repo: `zhongwen-anki-export-stats` hace exactamente esto (con detección automática del perfil, nombres de columna legibles y filtro opcional por mazo). Ver sección 1.2 más arriba.

## 4. Mejoras futuras a considerar

- **Audio de pronunciación**: generar un `.mp3` por palabra (TTS, p. ej. con
  `edge-tts` gratuito) y añadirlo como campo de audio — Anki lo reproduce
  automáticamente al mostrar la tarjeta. Muy recomendable para el oído, que
  ahora mismo no se entrena en absoluto.
- **Practicar también el carácter tradicional**: ahora mismo "Escribir Hanzi"
  solo entrena el simplificado; se podría añadir una variante o alternar.
- **`SynonymsESColored`**: los sinónimos en español no tienen versión con los
  caracteres coloreados por tono (sí la tienen en inglés); es una limitación
  menor, cosmética.
- **Actualizaciones seguras del mazo sin perder progreso**: `genanki` calcula
  el ID de cada nota a partir de sus campos — si en el futuro corriges el
  texto de una palabra ya estudiada, al reimportar Anki debería actualizar el
  contenido sin tocar tu progreso, pero conviene comprobarlo tras cada
  reimportación grande antes de fiarse a ciegas.
- **Automatizar la regeneración**: un script único (`make deck HSK1` o
  similar) que encadene `zhongwen-anki` + `zhongwen-anki-build-deck` para un
  nivel en un solo paso, en vez de dos comandos manuales.
- **Detección de vocabulario nuevo sin datos de trazos**: si se añaden
  palabras con caracteres sin datos de trazos descargados,
  `zhongwen-anki-build-hanzi-templates` avisa por consola exactamente qué
  caracteres faltan, pero no descarga el dato automáticamente — se podría
  automatizar la descarga bajo demanda.
- **Notas gramaticales**: HSK1 también exige un mínimo de gramática (no solo
  vocabulario); se podría añadir un mazo/nota complementaria con los puntos
  gramaticales básicos (p. ej. estructuras con 了, 吗, 的, clasificadores...).
- **Vocabulario real de HSK2 y HSK3**: la infraestructura para varios niveles
  ya existe (`data/hsk2/`, `data/hsk3/`, `--level`), pero las listas de
  palabras en sí siguen sin rellenar — hace falta repetir el proceso de
  búsqueda/verificación de vocabulario oficial + prompt LLM usado para HSK1.
