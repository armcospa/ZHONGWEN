# HSK4 (HSK 3.0)

- **Palabras:** 997 (solo las nuevas de este nivel), 801 caracteres distintos.
- **Fuente:** lista oficial *New HSK Vocabulary Level 4*.
- **Mazo:** [`decks/HSK4.apkg`](../../decks/HSK4.apkg), mazo `Chino - HSK4 (HSK 3.0)`, etiqueta `HSK4`.
- **Sinónimos:** 598 de 997 palabras los tienen.
- **Nivel en las tarjetas:** las respuestas muestran `HSK4` en la esquina superior izquierda.
- **Varias filas por carácter:** 生 (*shēng*) tiene dos acepciones con la misma lectura («dar a luz, producir» y «crudo»), y 重 (*chóng* / *zhòng*) y 空 (*kōng* / *kòng*) tienen dos lecturas. Cada fila es una nota distinta.

## Ficheros

| Fichero | Qué es |
|---|---|
| `input.tsv` | Vocabulario fuente, con el esquema descrito en [`CONTRIBUTING.md`](../../CONTRIBUTING.md#añadir-vocabulario-o-un-nivel-nuevo). La columna `Guid` es el identificador permanente de cada nota en Anki: no la edites. |
| `output.tsv` | Generado por `zhongwen-anki` (ignorado por git). |
| `input_cumulative.tsv` | Exploración previa que unía HSK1–HSK4 en un solo fichero (1.995 filas, columna `SourceLevel`). Se conserva como referencia; **no** forma parte del pipeline. |

## Regenerar

```bash
zhongwen-anki-build-all --levels HSK4
```

Si cambias plantillas o CSS, regenera todos los niveles (`zhongwen-anki-build-all` sin argumentos): comparten el mismo tipo de nota.
