# HSK3 (HSK 3.0)

- **Palabras:** 499 (solo las nuevas de este nivel), 480 caracteres distintos.
- **Fuente:** lista oficial *New HSK Vocabulary Level 3*.
- **Mazo:** [`decks/HSK3.apkg`](../../decks/HSK3.apkg), mazo `Chino - HSK3 (HSK 3.0)`, etiqueta `HSK3`.
- **Sinónimos:** solo 1 de 499 palabras los tiene; pendiente de completar.
- **Nivel en las tarjetas:** las respuestas muestran `HSK3` en la esquina superior izquierda.
- **Nota:** 站 (*zhàn*) está aquí como verbo («estar de pie, ponerse de pie»), igual que en la lista oficial; el sustantivo («estación, parada») es de HSK2.

## Ficheros

| Fichero | Qué es |
|---|---|
| `input.tsv` | Vocabulario fuente, con el esquema descrito en [`CONTRIBUTING.md`](../../CONTRIBUTING.md#añadir-vocabulario-o-un-nivel-nuevo). La columna `Guid` es el identificador permanente de cada nota en Anki: no la edites. |
| `output.tsv` | Generado por `zhongwen-anki` (ignorado por git). |

## Regenerar

```bash
zhongwen-anki-build-all --levels HSK3
```

Si cambias plantillas o CSS, regenera todos los niveles (`zhongwen-anki-build-all` sin argumentos): comparten el mismo tipo de nota.
