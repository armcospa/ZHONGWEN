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
  (`collection.anki2` → `revlog`) a un CSV limpio para analizarlo fuera de Anki,
  incluyendo por qué tipo de tarjeta fue cada repaso (`card_type`: "Hanzi ->
  Significado", "Significado -> Hanzi", "Escribir Pinyin", "Escribir Hanzi").
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

### 1.3 Tipo de nota "Chino - HSK (ES/EN)" — 6 tarjetas por palabra

El tipo de nota es **uno solo, compartido por todos los niveles** (HSK1,
HSK2, HSK3...); lo que distingue a cada nivel es el mazo (`Chino - HSK1
(HSK 3.0)`, `Chino - HSK2 (HSK 3.0)`...) y la etiqueta (`HSK1`, `HSK2`...)
de cada nota, ambos asignados por `zhongwen-anki-build-deck --level`.
| Tarjeta | Pregunta | Respuesta | Qué entrena |
|---|---|---|---|
| Hanzi → Significado | Carácter | Significado (ES, con EN de apoyo) | Lectura |
| Significado → Hanzi | Significado (ES, con EN de apoyo) | Carácter + pinyin | Producción |
| Pinyin → Significado | Pinyin con tonos (carácter oculto) | Carácter + significado | Reconocer la palabra solo por su pinyin, sin ver el hanzi |
| Significado → Pinyin | Significado (ES, con EN de apoyo) | Pinyin con tonos + carácter | Recordar cómo se pronuncia una palabra solo a partir de su significado, sin verla escrita |
| Escribir Pinyin | Carácter | Escribes el pinyin con tonos, Anki compara letra a letra | Ortografía del pinyin |
| Escribir Hanzi | Pinyin + significado | Dibujas el carácter trazo a trazo, evaluado automáticamente | Escritura |

`Pinyin -> Significado` (`card_template/pinyin_to_meaning/`, `ord=4`) y
`Significado -> Pinyin` (`card_template/english_to_pinyin/`, `ord=5`) son las
plantillas más nuevas -- ambas añadidas al *final* de la lista en
`build_deck.build_model` a propósito, para no reordenar los `ord` 0-3 (ni el
4) ya existentes y no romper el progreso/historial de tarjetas ya
importadas.

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
- **Análisis de tu propio aprendizaje**: `export_stats.py` (estable) da acceso
  a cada repaso individual (acierto/fallo, tipo de tarjeta de entre las 5,
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
   deck:"Chino - HSK1 (HSK 3.0)" card:"Escribir Pinyin"
   ```
4. Ajusta el límite de tarjetas si quieres (por defecto coge todas las que tocan repasar).
5. **Build**. Se crea un mazo temporal con solo esas tarjetas, sin duplicar nada — tu progreso real sigue en el mazo original y al vaciar el filtrado (`Empty`) las tarjetas vuelven a su sitio.

Puedes hacer lo mismo con `card:"Hanzi -> Significado"`, `card:"Significado -> Hanzi"`, `card:"Pinyin -> Significado"`, `card:"Significado -> Pinyin"` o `card:"Escribir Hanzi"` para las otras cinco.

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
separado en cada una de las 6 tarjetas del tipo de nota (§1.3).

**¿Cuántas nuevas al día?** Cada palabra es 1 nota con 6 tarjetas (una por
habilidad). Si metes N nuevas/día en cada habilidad, en la práctica introduces
6xN tarjetas nuevas al día, y cada una generará varios repasos futuros a
medida que Anki las reintroduzca -- la carga de repasos diarios crece durante
las primeras semanas hasta estabilizarse. Con 5/día por habilidad (30
tarjetas nuevas/día) se termina HSK1 (301 palabras) en ~2 meses, un ritmo
sostenible para 6 habilidades a la vez. No hace falta usar el mismo número en
las 6 -- si una habilidad cuesta más (p. ej. "Escribir Hanzi"), conviene meter
menos ahí que en las de reconocimiento. Para ajustar el número con datos
reales en vez de a ojo, usa `zhongwen-anki-export-stats` +
`zhongwen-anki-analyze-stats` (§1.2) después de 1-2 semanas y sube o baja
según si los repasos diarios se hacen pesados o sobra tiempo.

**Cómo montarlo, por cada habilidad:**
1. **Tools → Create Filtered Deck**, un nombre como `Nuevas - Hanzi -> Significado`.
2. **Search**:
   ```
   deck:"Chino - HSK1 (HSK 3.0)" card:"Hanzi -> Significado" is:new
   ```
   (cambia `card:"..."` por la habilidad que toque). El `is:new` es la parte
   clave -- sin él, un mazo filtrado normal solo trae tarjetas ya vencidas,
   no las que nunca se han visto.
3. **Order**: elige **"Order added"** (orden de creación) en vez de
   "Random" -- así cada reconstrucción trae siempre las siguientes tarjetas
   en orden estricto (1-5, luego 6-10, luego 11-15...), nunca al azar y nunca
   repetidas. Como todas las plantillas se crean en el mismo orden de fila
   del TSV, mantener el mismo ritmo (mismo número, mismo día) en las 6
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

**Uso recomendado en conjunto:** estos mazos "solo nuevas" son para
introducir palabras al ritmo elegido; para repasar lo que ya está aprendido,
se estudia el mazo normal `Chino - HSK1 (HSK 3.0)` tal cual -- ahí Anki
mezcla repasos de las 6 habilidades automáticamente, lo cual además ayuda a
la retención (mezclar habilidades en el repaso es mejor que bloquearlas).

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
