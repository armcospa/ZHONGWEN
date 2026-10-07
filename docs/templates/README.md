# Especificación de tarjetas y mazos

Los códigos usan `H` (hanzi), `P` (pinyin) y `M` (*meaning*): lo que va antes
del `2` se muestra y lo que va después se pide. `M` es el significado en el
idioma elegido con `--target-lang` (por defecto español), con el inglés de
apoyo.

| `ord` | Código | Anverso | Se pide | Fuente HTML |
|---|---|---|---|---|
| 0 | `H2M` | Hanzi | Recordar el significado | `h2m/` |
| 1 | `M2H` | Significado + caja de dibujo | Dibujar el hanzi (HanziWriter) | `m2h/` |
| 2 | `H2P` | Hanzi + caja de texto | Escribir el pinyin | `h2p/` |
| 3 | `PM2H` | Pinyin + significado + caja de dibujo | Dibujar el hanzi (HanziWriter) | `pm2h/` |
| 4 | `P2M` | Pinyin | Recordar el significado | `p2m/` |
| 5 | `M2P` | Significado + caja de texto | Escribir el pinyin | `m2p/` |
| 6 | `P2H` | Pinyin + caja de dibujo | Dibujar el hanzi (HanziWriter) | `p2h/` |
| 7 | `HM2P` | Hanzi + significado + caja de texto | Escribir el pinyin | `hm2p/` |
| 8 | `HP2M` | Hanzi + pinyin | Recordar el significado | `hp2m/` |
| 9 | `Toda la información` | Todos los campos | Nada (consulta) | `all_information/` |

Reglas de diseño:

- **Ningún anverso es igual a otro.** Cuando dos tarjetas muestran lo mismo,
  el modo de respuesta las distingue: caja de dibujo (hanzi), caja de texto
  (pinyin) o nada (significado).
- Los titulares usan siempre el **simplificado**. El tradicional solo aparece,
  marcado con `繁`, en `Toda la información`.
- Todas las respuestas muestran el nivel de la palabra (`SourceLevel`) en
  pequeño en la esquina superior izquierda, excepto HSK1, que es el nivel base.
- Todo lo que empieza oculto (pinyin de la definición y de la frase, versiones
  coloreadas) se puede mostrar con el botón **Unhide**.
- La respuesta de las tarjetas de dibujo anima el trazado correcto de cada
  carácter.
- Las tarjetas de escribir pinyin aceptan tildes (`àihào`) o números
  (`ai4hao4`), sin tener en cuenta mayúsculas, espacios ni apóstrofos, y
  muestran la solución en el formato que más usó el estudiante (tildes en
  caso de empate).

Los `ord` son la posición de cada plantilla y Anki asocia a ellos el historial
de cada tarjeta: solo se añaden tipos al final, nunca se reordenan. `ord` 0–5
existían antes de los códigos (`M2H` era «Significado → Hanzi» sin dibujo y
`M2P` no pedía escribir); `ord` 6–9 se añadieron en la versión 0.4.0.

Las piezas que comparten varias plantillas (detalles, botón **Unhide**,
nivel, HanziWriter) están en `card_template/_shared/` y se incluyen con
`<!-- include: nombre -->`; ver [`CONTRIBUTING.md`](../../CONTRIBUTING.md#plantillas-de-tarjeta).

## «Toda la información»

Es una vista de consulta, no de repaso. Como cualquier plantilla, genera una
tarjeta por nota. Con el itinerario recomendado no aparece nunca en los
repasos (el mazo principal tiene 0 nuevas y 0 repasos, y ningún mazo filtrado
la incluye). Si se estudia desde el mazo principal, conviene suspenderla:
`card:"Toda la información"` → **Suspender**.

## Mazos filtrados

[`template_mazos.txt`](template_mazos.txt) contiene el itinerario recomendado
de cuatro mazos filtrados (`PM2H`, `H2P`, `M2P`, `HP2M`). El resto de códigos
queda disponible para que cada estudiante cree sus propias rutas.
