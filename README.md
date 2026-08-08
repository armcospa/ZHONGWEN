# Zhongwen Anki

**Zhongwen Anki** es una herramienta en Python para generar mazos de Anki completos a partir de listas de vocabulario chino (HSK1, HSK2, HSK3...), pensada para estudiantes hispanohablantes. Combina contenido generado por un LLM (frases de ejemplo, sinónimos, definiciones) con procesado automático en Python (coloreado por tono, pinyin, escritura de trazos) para producir un mazo listo para importar en Anki.

Pensado para compartir: si solo quieres estudiar, no necesitas instalar nada — ver [Opción A](#opción-a--solo-quiero-estudiar-con-las-fichas-sin-instalar-nada) más abajo. Si quieres generar tu propio vocabulario o ampliar un nivel, ver [Opción B](#opción-b--quiero-generar-mi-propio-vocabulario-o-ampliar-un-nivel).

## Qué hace este repositorio

Por cada palabra china genera **5 tarjetas**:

| Tarjeta | Pregunta | Respuesta | Qué entrena |
|---|---|---|---|
| Hanzi → Significado | Carácter | Significado (ES, con EN de apoyo) | Lectura |
| Significado → Hanzi | Significado (ES, con EN de apoyo) | Carácter + pinyin | Producción |
| Pinyin → Significado | Pinyin con tonos (sin el carácter) | Carácter + significado | Comprensión oral/lectora del pinyin |
| Escribir Pinyin | Carácter | Escribes el pinyin con tonos; Anki lo compara letra a letra | Ortografía del pinyin |
| Escribir Hanzi | Pinyin + significado | Dibujas el carácter trazo a trazo, con [HanziWriter](https://hanziwriter.org/) validando forma, dirección y orden de cada trazo | Escritura a mano |

Además de esas 5 preguntas, cada tarjeta muestra pinyin con tonos, caracteres coloreados por tono, hasta 3 sinónimos y una definición corta en chino. El botón **"Unhide"** revela las secciones ocultas (pinyin y coloreado), para poder intentar leer o escribir antes de comprobar la respuesta.

### Ejemplos

**De inglés/español a chino:**
<div style="display: flex; justify-content: center; gap: 20px; flex-wrap: wrap;">
  <img src="resources/en_zh_桥梁_front.jpg" alt="Front" style="width: 32%;">
  <img src="resources/en_zh_桥梁_back_hidden.jpg" alt="Back Hidden" style="width: 32%;">
  <img src="resources/en_zh_桥梁_back.jpg" alt="Back" style="width: 32%;">
</div>

**De chino a inglés/español:**
<div style="display: flex; justify-content: center; gap: 20px; flex-wrap: wrap;">
  <img src="resources/zh_en_下划线_front.jpg" alt="Front" style="width: 32%;">
  <img src="resources/zh_en_下划线_back_hidden.jpg" alt="Back Hidden" style="width: 32%;">
  <img src="resources/zh_en_下划线_back.jpg" alt="Back" style="width: 32%;">
</div>

## Cómo funciona por dentro

El proceso completo es una cadena de 3 pasos, cada uno un script de Python bajo [`src/zhongwen_anki/`](src/zhongwen_anki/):

1. **[`enrich.py`](src/zhongwen_anki/enrich.py)** (comando `zhongwen-anki`) — coge un TSV "crudo" (palabra, traducciones y frase de ejemplo, generado con ayuda de un LLM — ver [Opción B](#opción-b--quiero-generar-mi-propio-vocabulario-o-ampliar-un-nivel)) y lo enriquece: colorea los caracteres por tono, y genera automáticamente el pinyin de frases y definiciones (`jieba` para segmentar palabras, `pypinyin` para el pinyin con tonos). El resultado es un segundo TSV con todas las columnas que necesitan las tarjetas.
2. **[`build_hanzi_templates.py`](src/zhongwen_anki/build_hanzi_templates.py)** (comando `zhongwen-anki-build-hanzi-templates`) — mira qué caracteres aparecen en el vocabulario (de todos los niveles a la vez) y regenera las plantillas HTML de "Escribir Hanzi", incrustando los datos de trazos de cada carácter directamente como texto estático dentro del HTML (para que funcione de forma fiable incluso en AnkiDroid, que a veces no carga a tiempo los ficheros multimedia externos).
3. **[`build_deck.py`](src/zhongwen_anki/build_deck.py)** (comando `zhongwen-anki-build-deck`) — empaqueta el TSV enriquecido junto con las plantillas HTML/CSS de [`card_template/`](card_template/) en un único `.apkg`, el formato que Anki importa.

El resultado ya compilado de este proceso para HSK1 vive en [`decks/HSK1.apkg`](decks/HSK1.apkg) — no hace falta ejecutar nada de esto si solo quieres estudiar.

Hay un cuarto script, **[`export_stats.py`](src/zhongwen_anki/export_stats.py)** (comando `zhongwen-anki-export-stats`), que no forma parte de la cadena de generación: lee tu propio historial de repasos de Anki y lo exporta a CSV para analizarlo (ver [Analizar tu propio progreso](#analizar-tu-propio-progreso)).

### Estructura del proyecto

```
zhongwen-anki/
├── src/zhongwen_anki/          # Paquete Python instalable (los 4 scripts anteriores)
├── card_template/               # HTML/CSS de las 5 tarjetas + librería HanziWriter
├── data/
│   ├── hsk1/input.tsv            # Vocabulario HSK1 (301 palabras, completo)
│   ├── hsk2/, hsk3/               # Preparadas para rellenar (ver README de cada carpeta)
├── decks/                        # Mazos .apkg ya generados, listos para importar
├── tests/                        # Suite de pytest
├── docs/FUNCIONALIDADES.md       # Documentación ampliada (en español)
└── resources/                    # Capturas de pantalla
```

## Opción A — Solo quiero estudiar con las fichas (sin instalar nada)

Este es el camino pensado para compartir el mazo con amigos que no van a tocar código:

1. Instalar [Anki](https://apps.ankiweb.net/) (Windows, macOS, Android, iOS) y, si quieres sincronizar entre varios dispositivos, crear una cuenta.
2. Descargar este repositorio: en GitHub, botón **Code → Download ZIP** (o `git clone` si prefieres la línea de comandos), y descomprimirlo.
3. Abrir Anki → `Archivo > Importar` → seleccionar el archivo [`decks/HSK1.apkg`](decks/HSK1.apkg) dentro de la carpeta descargada.
4. Empezar a repasar. Usa el botón **"Unhide"** en las tarjetas para revelar pinyin y coloreado antes de comprobar tu respuesta.

No hace falta instalar Python, ni ningún paquete, ni ejecutar ningún comando para esto.

## Opción B — Quiero generar mi propio vocabulario o ampliar un nivel

Este camino sí requiere el entorno de Python, porque implica ejecutar los 3 scripts descritos en [Cómo funciona por dentro](#cómo-funciona-por-dentro).

### Instalación

Requiere Python 3.10+.

```bash
git clone <url-de-tu-fork>
cd zhongwen-anki
python -m venv .venv
.venv\Scripts\activate       # Windows; en macOS/Linux: source .venv/bin/activate
pip install -e ".[deck,test]"
```

Esto instala la librería y registra los siguientes comandos en tu entorno virtual:

| Comando | Qué hace |
|---|---|
| `zhongwen-anki` | Enriquece un `input.tsv` (pinyin, coloreado, traducción) |
| `zhongwen-anki-build-deck` | Empaqueta un `output.tsv` en un `.apkg` |
| `zhongwen-anki-build-hanzi-templates` | Regenera las plantillas de escritura de hanzi |
| `zhongwen-anki-export-stats` | Exporta tu historial de repasos de Anki a CSV |

### Paso 1: Preparar la lista de palabras

Crea un archivo de texto con las palabras chinas que quieres estudiar. La [extensión Zhongwen](#herramientas-adicionales) es una forma rápida de ir construyendo esta lista mientras navegas.

```
向量 vector
矩阵 matrix
...
```

### Paso 2: Generar el contenido con un LLM

Copia el siguiente prompt, sustituye `<IDIOMA_DESTINO>` por tu idioma nativo (por defecto, y para lo que están pensadas las plantillas de este repositorio, **español**), añade tu lista de palabras al final, y envíalo a un LLM (ChatGPT 4.1 o superior da mejores resultados con el formato que GPT-4 a secas).

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
Si una palabra tiene varios significados comunes, elige el más general según el uso habitual; no intentes cubrir todos los significados.

Responde en un bloque de código TSV, sin generar código como tal, sin usar Python ni pandas.

-----

### Lista de palabras

<<LISTA DE PALABRAS AQUÍ>>
~~~

[Aquí](./data/hsk1/input.tsv) tienes un ejemplo real de lista generada (HSK1, en español).

> **¿Otro idioma que no sea español?** El pipeline no está atado a español en el código: es un sufijo de columna configurable (`--target-lang`, ver paso 4). Puedes usar el mismo prompt cambiando `<IDIOMA_DESTINO>` por cualquier idioma; solo tendrás que adaptar también los textos fijos de las plantillas HTML en `card_template/` (que sí están escritos en español, ya que es el idioma principal de este fork).

### Paso 3: Guardar la lista generada

Guarda la tabla TSV que te devolvió el LLM como `data/hsk1/input.tsv` (o `data/hsk2/input.tsv`, `data/hsk3/input.tsv` si estás rellenando otro nivel — ver también [Cómo añadir un nuevo nivel](#cómo-añadir-un-nuevo-nivel-hsk2-hsk3)).

### Paso 4: Regenerar las plantillas de escritura de hanzi

Necesario la primera vez y cada vez que el vocabulario de cualquier nivel incorpore caracteres nuevos:

```bash
zhongwen-anki-build-hanzi-templates
```

Escanea automáticamente **todos** los `data/*/input.tsv` que encuentre (todos los niveles), porque el tipo de nota de "Escribir Hanzi" es el mismo para todos.

### Paso 5: Generar el TSV enriquecido

```bash
zhongwen-anki -i data/hsk1/input.tsv -o data/hsk1/output.tsv
```

Esto es exactamente el paso 1 de [Cómo funciona por dentro](#cómo-funciona-por-dentro): colorea los caracteres por tono, genera automáticamente el pinyin de frases y definiciones, y añade las columnas derivadas que usan las tarjetas.

Por defecto lee/escribe las traducciones en las columnas `*ES` (español). Para otro idioma:

```bash
zhongwen-anki -i data/hsk2/input.tsv -o data/hsk2/output.tsv --target-lang FR
```

### Paso 6: Empaquetar el mazo

```bash
zhongwen-anki-build-deck -i data/hsk1/output.tsv -o decks/HSK1.apkg --level HSK1
```

`--level` fija el nombre del mazo y la etiqueta (`HSK1`, `HSK2`, `HSK3`...) de cada nota.

### Paso 7: Importar en Anki

`Archivo > Importar` y selecciona el `.apkg` que acabas de generar. Anki actualizará las notas existentes (mismo tipo de nota, mismos IDs) sin perder tu progreso si ya lo habías importado antes.

## Cómo añadir un nuevo nivel (HSK2, HSK3...)

La infraestructura para varios niveles ya existe; falta el vocabulario en sí:

1. Rellena `data/hsk2/input.tsv` (o `data/hsk3/`) con el mismo esquema que `data/hsk1/input.tsv` — ver el `README.md` de esa carpeta, o repite los pasos 1-3 de la Opción B.
2. `zhongwen-anki-build-hanzi-templates` (añade los caracteres nuevos a las plantillas compartidas).
3. `zhongwen-anki -i data/hsk2/input.tsv -o data/hsk2/output.tsv`
4. `zhongwen-anki-build-deck -i data/hsk2/output.tsv -o decks/HSK2.apkg --level HSK2`

`HSK1`, `HSK2` y `HSK3` ya tienen un ID de mazo reservado en `DECK_IDS` (`src/zhongwen_anki/build_deck.py`); para ir más allá de HSK3 basta con añadir una entrada nueva ahí (debe ser estable: no cambies el ID de un nivel que ya hayas compartido, o el siguiente reimport creará un mazo duplicado en vez de actualizar el existente).

## Ajustes recomendados en Anki

<details>
<summary>Configuración de mazo usada en este repositorio (ajústala a tu gusto)</summary>

```
# Límites diarios
Tarjetas nuevas/día = 5
Repasos máximos/día = 100

# Tarjetas nuevas
Pasos de aprendizaje = 1m 10m 1d 6d
Intervalo de graduación = 7
Intervalo fácil = 10
Orden de inserción = Aleatorio

# Fallos
Pasos de re-aprendizaje = 10m 20m
Intervalo mínimo = 2
Umbral de sanguijuela = 5
Acción de sanguijuela = Solo etiquetar

# Avanzado
Intervalo máximo = 365
Facilidad inicial = 2.50
Bonus fácil = 1.30
Modificador de intervalo = 1.10
Intervalo difícil = 1.20
Nuevo intervalo = 0.80
```
</details>

Complementos recomendados: **[Auto Ease Factor](https://ankiweb.net/shared/info/1672712021)** o **[Reset Ease](https://ankiweb.net/shared/info/947935257)** (evitan la "ease hell"), y **[Review Heatmap](https://ankiweb.net/shared/info/1771074083)** (visualiza tu constancia).

## Herramientas adicionales

[Zhongwen Browser Extension](https://github.com/cschiller/zhongwen) es un diccionario chino emergente para Chrome/Firefox — pulsa `R` sobre una palabra para añadirla a tu lista de vocabulario, y `Alt+W` para verla. Muy útil para construir la lista de palabras del paso 1 de la Opción B.

## Analizar tu propio progreso

```bash
zhongwen-anki-export-stats --deck "HSK1" -o data/anki_reviews.csv
```

Exporta cada repaso individual (acierto/fallo, tiempo empleado, intervalo) directamente desde `collection.anki2`, para analizarlo fuera de Anki (por nivel, por tipo de tarjeta, por palabra...). Ver [`docs/FUNCIONALIDADES.md`](docs/FUNCIONALIDADES.md) para más detalle y trucos de uso dentro de Anki (mazos filtrados, reordenar tarjetas, resetear historial...).

## Tests

```bash
pytest
```

## Créditos y licencia

Basado en el proyecto original [`zhongwen-anki`](https://github.com/thomashirtz/zhongwen-anki) de Thomas Hirtz. La tarjeta de escritura de hanzi usa [HanziWriter](https://hanziwriter.org/) (MIT) y datos de trazos derivados de [Make Me a Hanzi](https://github.com/skishore/makemeahanzi) (licencia Arphic Public — ver [`card_template/hanzi_writing/NOTICE.md`](card_template/hanzi_writing/NOTICE.md)).

Distribuido bajo licencia MIT — ver [`LICENSE`](LICENSE).
