# Funcionalidades, posibilidades y mejoras futuras

Este documento resume todo lo que se ha construido sobre el repositorio original
`zhongwen-anki` para estudiar el vocabulario obligatorio de **HSK (estándar 3.0,
vigente desde julio de 2026)**, qué hace cada pieza, qué puertas abre, y qué se
podría mejorar más adelante. El pipeline es el mismo para cualquier nivel;
hay vocabulario completo de **HSK1 (301 palabras), HSK2 (198), HSK3 (499) y
HSK4 (997)**, cada nivel con solo sus palabras nuevas.

## 1. Qué hay implementado

### 1.1 Generación del vocabulario (`data/<nivel>/input.tsv`)
- Cada nivel vive en su propia carpeta: `data/hsk1/input.tsv` (301 palabras
  oficiales de HSK1 3.0 (2026), extraídas del PDF de Khanji School /
  Chinesimple y verificadas una por una), `data/hsk2/`, `data/hsk3/` y
  `data/hsk4/` (ver el `README.md` de cada carpeta).
- Cada palabra lleva además un `Guid` congelado: el identificador con el que
  Anki reconoce la nota al reimportar, para que corregir una palabra nunca
  la duplique ni le haga perder el progreso (ver `CONTRIBUTING.md`).
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
- `zhongwen-anki-build-all`: regenera el `output.tsv` y el `.apkg` de todos
  los niveles en una sola pasada. Es la forma recomendada de publicar: el tipo
  de nota es el mismo para todos los niveles, así que deben generarse juntos.
  Los datos de trazos de HanziWriter se incrustan automáticamente con los
  caracteres de **todos** los `data/<nivel>/input.tsv`.
- `zhongwen-anki-export-stats`: exporta el historial de repasos de Anki
  (`collection.anki2` → `revlog`) a un CSV limpio para analizarlo fuera de Anki,
  incluyendo por qué tipo de tarjeta fue cada repaso (`card_type`: `H2M`,
  `M2H`, `H2P`, `PM2H` y el resto de códigos de tarjeta).
- `zhongwen-anki-analyze-stats`: lee ese CSV y genera un informe HTML
  autocontenido (gráficos incrustados como PNG en base64, sin dependencias
  externas ni conexión a internet) con precisión por tipo de tarjeta y por
  nivel, tendencia de aciertos (media móvil de 7 días), retención por
  intervalo desde el repaso anterior, precisión por día de la semana, y una
  tabla de las palabras con peor ratio de aciertos (candidatas a repaso
  dirigido). Requiere `pip install -e ".[analyze]"` (o `.[test]`, que ya lo
  incluye).
- Todo corre en un entorno virtual local (`.venv/`), sin tocar el Python
  global. Instalación: `pip install -e ".[deck,test]"`.

### 1.3 Tipo de nota "Chino - HSK (ES/EN)" — 10 tarjetas por palabra

El tipo de nota es **uno solo, compartido por todos los niveles** (HSK1,
HSK2, HSK3...); lo que distingue a cada nivel es el mazo (`Chino - HSK1
(HSK 3.0)`, `Chino - HSK2 (HSK 3.0)`...) y la etiqueta (`HSK1`, `HSK2`...)
de cada nota, ambos asignados por `zhongwen-anki-build-deck --level`.
| Tarjeta | Pregunta | Respuesta | Qué entrena |
|---|---|---|---|
| `H2M` | Hanzi | Meaning | Lectura |
| `M2H` | Meaning | Dibujas hanzi trazo a trazo | Producción escrita |
| `H2P` | Hanzi | Escribes pinyin | Ortografía del pinyin |
| `PM2H` | Pinyin + meaning | Dibujas hanzi trazo a trazo | Escritura |
| `P2M` | Pinyin | Meaning | Comprensión del pinyin |
| `M2P` | Meaning | Escribes pinyin | Producción de pinyin |
| `P2H` | Pinyin | Dibujas hanzi trazo a trazo | Del sonido a la escritura |
| `HM2P` | Hanzi + meaning | Escribes pinyin | Pinyin con pista semántica |
| `HP2M` | Hanzi + pinyin | Meaning | Meaning con pista fonética |
| `Toda la información` | Todos los campos | Consulta | Sin evaluación |

En las tarjetas de escribir pinyin vale tanto `àihào` como `ai4hao4`; la
corrección se muestra en el formato que hayas usado.

Los códigos `H`, `P` y `M` significan hanzi, pinyin y *meaning*. Los seis
primeros conservan los `ord` 0–5 históricos; `P2H`, `HM2P`, `HP2M` y `Toda
la información` se añadieron al final para no alterar ningún historial ya
importado. Las respuestas de HSK2, HSK3 y HSK4 muestran en pequeño, arriba a
la izquierda, el nivel en el que se incorporó la palabra. Consulta
[`templates/README.md`](templates/README.md) para la relación completa con
los archivos HTML.

Las tarjetas de escritura de hanzi (`PM2H`, `M2H` y `P2H`) usan
**[HanziWriter](https://hanziwriter.org/)** (librería JS de código abierto)
con los datos de trazos de cada uno de los 1.096 caracteres únicos usados en
HSK1–HSK4. Tanto la librería como los datos de trazos van **incrustados
directamente como texto estático** en esas plantillas (nada de `<script src>` externo, ni `fetch()`, ni
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
  búsqueda `card:H2P`) — sin duplicar datos ni progreso. Puedes combinar
  varios niveles a la vez: `deck:"Chino - HSK*" card:H2P`.
- Sincronización Anki Desktop ↔ AnkiWeb ↔ AnkiDroid con una sola cuenta.

## 2. Qué posibilidades abre esto

- **Escalar a otros niveles (ya implementado hasta HSK4)**: el pipeline
  entero (`data/<nivel>/input.tsv` → `zhongwen-anki` → `build-deck --level`)
  es genérico; añadir HSK5 es cuestión de crear `data/hsk5/input.tsv` con el
  mismo esquema, añadir una entrada en `DECK_IDS` dentro de `build_deck.py` y
  ejecutar `zhongwen-anki-build-all` (ver `CONTRIBUTING.md`).
- **Análisis de tu propio aprendizaje**: `export_stats.py` (estable) da acceso
  a cada repaso individual (acierto/fallo, tipo de tarjeta de entre las 10,
  tiempo empleado, facilidad, intervalo). `analyze_stats.py` (🚧 WIP, ver
  §1.2) convierte eso en un informe HTML: qué palabras cuestan más, cómo
  evoluciona tu ritmo de aciertos, si fallas más en pinyin que en escritura,
  en qué días de la semana rindes mejor, y si Anki te está espaciando los
  repasos demasiado agresivo (precisión que cae en los intervalos largos).
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
   deck:"Chino - HSK1 (HSK 3.0)" card:H2P
   ```
4. Ajusta el límite de tarjetas si quieres (por defecto coge todas las que tocan repasar).
5. **Build**. Se crea un mazo temporal con solo esas tarjetas, sin duplicar nada — tu progreso real sigue en el mazo original y al vaciar el filtrado (`Empty`) las tarjetas vuelven a su sitio.

Puedes hacer lo mismo con cualquier código: `H2M`, `M2H`, `PM2H`, `P2M`,
`M2P`, `P2H`, `HM2P` o `HP2M`. El itinerario recomendado de cuatro mazos
está en [`templates/template_mazos.txt`](templates/template_mazos.txt).

**Solución de problemas — "No se encontraron tarjetas coincidentes":**
- Lo más probable es que tu colección de Anki todavía no tenga importada la versión del mazo que incluye ese código — reimporta el `.apkg` más reciente de [`decks/`](../decks/) primero.
- Comprueba el nombre exacto del mazo y de la plantilla desde **Browse**: en la barra lateral izquierda, despliega "Decks" y "Card Types" y haz clic en el que quieras — Anki rellena la búsqueda automáticamente con la sintaxis correcta.
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
4. Alternativa ya hecha en este repo: `zhongwen-anki-export-stats` hace exactamente esto (con detección automática del perfil, nombres de columna legibles y filtro opcional por mazo), y `zhongwen-anki-analyze-stats` convierte ese CSV en un informe HTML con gráficos. Ver sección 1.2 más arriba.

### 3.5 Flujo si estudias sobre todo en AnkiDroid

Ambos comandos leen `collection.anki2`, que vive en el ordenador con Anki
Desktop -- no en el móvil. El flujo recomendado si la mayoría de tu estudio es
en AnkiDroid:

1. En AnkiDroid: sincroniza (icono de sincronización) para subir tus repasos a AnkiWeb.
2. En el ordenador con Anki Desktop: sincroniza también (mismo icono, o `Y`), para bajar esos repasos al `collection.anki2` local.
3. `zhongwen-anki-export-stats` (regenera `data/anki_reviews.csv` con todo lo nuevo).
4. `zhongwen-anki-analyze-stats` (regenera `data/report.html`).

Como los repasos se acumulan (nunca se borran salvo que hagas `Forget`), es
seguro repetir este flujo cuando quieras -- cada vez parte del historial
completo, no incremental.

### 3.6 Introducir tarjetas nuevas a tu ritmo, por habilidad

Los mazos filtrados no solo sirven para repasar por habilidad (§3.1) -- también
sirven para controlar cuántas palabras nuevas quieres estrenar cada día, por
separado en cada una de las tarjetas que decidas estudiar (§1.3).

**¿Cuántas nuevas al día?** Cada palabra es 1 nota con 10 tarjetas posibles.
Si metes N nuevas/día en cada una de las cuatro habilidades recomendadas,
introduces 4xN tarjetas nuevas al día, y cada una generará varios repasos futuros a
medida que Anki las reintroduzca -- la carga de repasos diarios crece durante
las primeras semanas hasta estabilizarse. Con 5/día por habilidad (20
tarjetas nuevas/día) se termina HSK1 (301 palabras) en ~2 meses, un ritmo
sostenible para las cuatro habilidades recomendadas. No hace falta usar el mismo número en
todas -- si una habilidad cuesta más (p. ej. `PM2H`), conviene meter
menos ahí que en las de reconocimiento. Para ajustar el número con datos
reales en vez de a ojo, usa `zhongwen-anki-export-stats` +
`zhongwen-anki-analyze-stats` (§1.2) después de 1-2 semanas y sube o baja
según si los repasos diarios se hacen pesados o sobra tiempo.

**Cómo montarlo, por cada habilidad:**
1. **Tools → Create Filtered Deck**, un nombre como `Nuevas - H2M`.
2. **Search**:
   ```
   deck:"Chino - HSK1 (HSK 3.0)" card:H2M is:new
   ```
   (cambia `card:"..."` por la habilidad que toque). El `is:new` es la parte
   clave -- sin él, un mazo filtrado normal solo trae tarjetas ya vencidas,
   no las que nunca se han visto.
3. **Order**: elige **"Order added"** (orden de creación) en vez de
   "Random" -- así cada reconstrucción trae siempre las siguientes tarjetas
   en orden estricto (1-5, luego 6-10, luego 11-15...), nunca al azar y nunca
   repetidas. Como todas las plantillas se crean en el mismo orden de fila
   del TSV, mantener el mismo ritmo (mismo número, mismo día) en las habilidades elegidas
   mantiene las tandas de las distintas habilidades sincronizadas sobre las
   mismas palabras.
4. **Cards selected by this filter**: el número del día (normalmente 5; se
   puede subir puntualmente para ponerse al día o adelantar varias tandas de
   golpe -- Anki calcula solo qué corresponde, nunca hay que indicar el rango
   a mano).
5. **Build**.

Se repite para cada habilidad en la que se quiera controlar el ritmo de
nuevas por separado.

**Mecánica de `is:new` (preguntas frecuentes):**
- *¿Pueden volver a salir las de ayer?* No. `is:new` solo empareja tarjetas
  que nunca se han contestado; en cuanto se responde una (aunque sea dentro
  de un mazo filtrado) deja de ser "nueva" para siempre. El número en "Cards
  selected" solo decide cuántas de las que **todavía quedan** se incluyen esa
  vez.
- *¿Se pierden las estadísticas o el progreso?* No. Contestar dentro de un
  mazo filtrado se registra en el `revlog` igual que en el mazo normal (con
  "Reschedule cards based on my answers" activado, el valor por defecto).
  Cuando una tarjeta ya no encaja en la búsqueda, vuelve sola a su mazo de
  origen con el progreso intacto. Los repasos a corto plazo de una tarjeta
  recién introducida (a los 10 min / 1 día) no aparecen dentro de este mismo
  mazo "solo nuevas" -- su búsqueda es estrictamente `is:new` -- saldrán en
  la sesión normal del mazo `Chino - HSK1`, mezclados con el resto.
- *¿Y cuando se acaban las palabras de ese nivel?* Reconstruir con cualquier
  número no trae nada -- no es un error, solo significa que ya se han
  introducido las 301 palabras de HSK1 en esa habilidad; de ahí en adelante
  solo hay repasos normales (hasta subir de nivel o hacer `Forget`, §3.3). Si
  se pide más de las que quedan (p. ej. 10 y solo hay 3), Anki da esas 3 sin
  fallar.

**¿Cuándo se "regenera" un mazo filtrado?** Nunca solo -- no hay ningún
temporizador ni corte de día interno para esto. Un mazo filtrado se queda
exactamente como se construyó hasta que se pulsa **Rebuild** (reconstruir) a
mano; se puede hacer tantas veces al día como se quiera (al terminar una
sesión, dos horas después, o cinco veces en un día), porque `is:new` es un
estado, no una fecha. El único corte de día que existe en Anki (Preferences →
Scheduling → "Next day starts at", 4am por defecto) solo afecta al contador
de "New cards/day" de un mazo normal -- irrelevante aquí, porque el número se
pone a mano cada vez.
- **Anki Desktop**: clic en el mazo filtrado → engranaje ⚙️ → **Rebuild**.
- **AnkiDroid / AnkiMobile**: abrir el mazo filtrado desde la lista y pulsar
  el icono de reconstruir (flecha circular) arriba.

**Dos formas de combinarlo:**
- *Itinerario recomendado* (el del README y
  [`templates/template_mazos.txt`](templates/template_mazos.txt)): cada mazo
  filtrado lleva dos búsquedas, una de repasos (`is:due`) y otra de nuevas
  (`is:new`), y el mazo principal se deja con 0 nuevas y 0 repasos al día.
  Cada habilidad se repasa por separado y solo se estudian los tipos de
  tarjeta elegidos.
- *Alternativa*: mazos filtrados solo de nuevas, como los de esta sección, y
  los repasos en el mazo normal `Chino - HSK1 (HSK 3.0)` tal cual, donde Anki
  mezcla los repasos de todas las habilidades (mezclarlas ayuda a la
  retención). En ese caso, suspende las tarjetas de los tipos que no quieras
  estudiar (por ejemplo `card:"Toda la información"`), porque si no el mazo
  normal también te las presentará.

## 4. Mejoras futuras a considerar

- **Audio de pronunciación**: generar un `.mp3` por palabra (TTS, p. ej. con
  `edge-tts` gratuito) y añadirlo como campo de audio — Anki lo reproduce
  automáticamente al mostrar la tarjeta. Muy recomendable para el oído, que
  ahora mismo no se entrena en absoluto.
- **Practicar también el carácter tradicional**: ahora mismo `PM2H`
  solo entrena el simplificado; se podría añadir una variante o alternar.
- **Detección de vocabulario nuevo sin datos de trazos**: si se añaden
  palabras con caracteres sin datos de trazos descargados, la generación del
  mazo avisa exactamente de qué caracteres faltan, pero no descarga el dato
  automáticamente; se podría automatizar la descarga bajo demanda.
- **Completar los sinónimos**: HSK3 solo tiene 1 de 499 y HSK2, 14 de 198;
  se podría repetir el prompt del LLM solo para esas columnas.
- **Notas gramaticales**: HSK1 también exige un mínimo de gramática (no solo
  vocabulario); se podría añadir un mazo/nota complementaria con los puntos
  gramaticales básicos (p. ej. estructuras con 了, 吗, 的, clasificadores...).
- **Vocabulario de HSK5 y HSK6**: repetir el proceso de búsqueda y
  verificación del vocabulario oficial y el prompt del LLM usados para
  HSK1–HSK4.
