# HSK2 (HSK 3.0)

- **Palabras:** 198 (solo las nuevas de este nivel), 200 caracteres distintos.
- **Fuente:** lista oficial *New HSK Vocabulary Level 2*.
- **Mazo:** [`decks/HSK2.apkg`](../../decks/HSK2.apkg), mazo `Chino - HSK2 (HSK 3.0)`, etiqueta `HSK2`.
- **Sinónimos:** solo 14 de 198 palabras los tienen; pendiente de completar.
- **Nivel en las tarjetas:** las respuestas muestran `HSK2` en la esquina superior izquierda.
- **Nota:** 站 (*zhàn*) está aquí como sustantivo («estación, parada»), igual que en la lista oficial; el verbo («estar de pie») es de HSK3.

## Ficheros

| Fichero | Qué es |
|---|---|
| `input.tsv` | Vocabulario fuente, con el esquema descrito en [`CONTRIBUTING.md`](../../CONTRIBUTING.md#añadir-vocabulario-o-un-nivel-nuevo). La columna `Guid` es el identificador permanente de cada nota en Anki: no la edites. |
| `output.tsv` | Generado por `zhongwen-anki` (ignorado por git). |

## Regenerar

```bash
zhongwen-anki-build-all --levels HSK2
```

Si cambias plantillas o CSS, regenera todos los niveles (`zhongwen-anki-build-all` sin argumentos): comparten el mismo tipo de nota.
