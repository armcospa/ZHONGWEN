# HSK1 (HSK 3.0)

- **Palabras:** 301 (solo las nuevas de este nivel), 248 caracteres distintos.
- **Fuente:** lista oficial de HSK1 3.0 (2026), extraída del PDF de Khanji School / Chinesimple y verificada palabra por palabra.
- **Mazo:** [`decks/HSK1.apkg`](../../decks/HSK1.apkg), mazo `Chino - HSK1 (HSK 3.0)`, etiqueta `HSK1`.
- **Sinónimos:** 134 de 301 palabras los tienen.

## Ficheros

| Fichero | Qué es |
|---|---|
| `input.tsv` | Vocabulario fuente, con el esquema descrito en [`CONTRIBUTING.md`](../../CONTRIBUTING.md#añadir-vocabulario-o-un-nivel-nuevo). La columna `Guid` es el identificador permanente de cada nota en Anki: no la edites. |
| `output.tsv` | Generado por `zhongwen-anki` (ignorado por git). |

## Regenerar

```bash
zhongwen-anki-build-all --levels HSK1
```

Si cambias plantillas o CSS, regenera todos los niveles (`zhongwen-anki-build-all` sin argumentos): comparten el mismo tipo de nota.
