# Prompts de caja y de punto de SAM 3.1 (smoke test, 27 oct)

Preparación de los puntos B (Spark localiza, SAM corta) y C (SAM con clic) del segundo análisis.
Fuente: https://dev.meta.ai/docs/sam/segmenting, sección "Prompt with boxes and points", leída el 27 oct.
Script: `scripts/smoke_sam_prompts.py`, que pasa por `meta_client.segment_row_raw` (la misma llamada y la misma caché de siempre).
Evidencia: `docs/sam-prompts/sam_prompts.json` y las dos imágenes de esta carpeta.

## Lo que dice la doc
- El prompt va en el mismo `input_text`, con la gramática de la salida: `<0f>` abre el cuadro 0 (una imagen solo usa `<0f>`), luego objetos separados por comas, cada uno con un id nuestro y sus tokens.
- Caja: `<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|>`, x2 y y2 incluidos, una caja por objeto.
- Punto positivo: `<|point;x=..;y=..;w=..;h=..|>`. Negativo: el mismo token con `-` antes. Solo los puntos pueden ser negativos.
- `w` y `h` son el tamaño en pixeles de la imagen enviada, iguales en todos los tokens. Si la proporción no coincide con la imagen, la API devuelve 400.
- Máximo 16 objetos por petición. No se mezcla frase y cajas o puntos en un mismo prompt.
- Con cajas o puntos la máscara siempre llega en `one_bit` (marcador `!`), sin importar `mask_encoding`.
- `metadata.include_confidence: "true"` también da `c` con cajas y puntos.

## Prueba con la API real
Foto: Nevada Test Site U12G, caja 1 (U.S. DOE, dominio público). Fila 1 recortada por `calibration.py`: 2500 x 278 px.

| Prompt | Texto enviado | Respuesta | Tiempo |
|---|---|---|---|
| Concepto (el de hoy) | `stone` | 13 piezas, confianza 0.55 a 0.82 | caché |
| Caja sobre una pieza | `<0f>1<\|box;x1=314;y1=41;x2=500;y2=268;w=2500;h=278\|>` | 1 registro, id 1, caja 313-499, confianza 0.95, máscara `!` | 3.7 s |
| Punto positivo y negativo | `<0f>2<\|point;x=722;y=161;w=2500;h=278\|>-<\|point;x=965;y=161;w=2500;h=278\|>` | 1 registro, id 2, confianza 0.95, máscara `!` | 3.3 s |

Lo que confirma:
- La respuesta llega bajo nuestros ids (1 y 2), así que se puede ligar cada máscara con la caja de Spark o con el clic del geólogo.
- `parse_sam_text` y `sam_masks` de `meta_client` leen la respuesta sin cambios: el `<0f>` del inicio y la `c` en caja y máscara no les estorban.
- Un clic tarda unos 3 a 4 s por fila. Para C cabe en la revisión si se muestra que SAM está trabajando.
- La caja que devuelve el prompt de punto (x 331 a 962) es más ancha que la pieza marcada. La máscara sí queda en la pieza (ver `sam_prompt_point.jpg`). Para C hay que medir con la máscara y no con la caja.

Hallazgo para B: en la fila 2 de esta misma caja, `stone` devuelve cero objetos (la respuesta vacía está en caché). Es la falla de Nevada que B ataca: Spark localiza las piezas y SAM corta con cajas.

Hecho el 28 oct: el constructor de prompts en `meta_client.py` (`sam_prompt` y `grid_box_to_pixels`), con tests nuestros (`tests/test_sam_prompts.py`) e implementación de Muse Code (traza `docs/muse-code/sam-prompts-1.json`).

## B: Spark localiza, SAM corta (28 oct)

`MetaClient.locate_row` pide a Muse Spark las cajas de cada objeto de la fila con la localización de https://dev.meta.ai/docs/image-understanding (cuadrícula 0 a 1000, salida estructurada `RowLocation`, validada con Pydantic). Clases: `core`, `run_block`, `card`, `waxed_sample`, `other`. `segmentation.located_masks` manda las cajas de núcleo a SAM 3.1 como prompts de caja (16 por petición) y quita de la longitud lo demás. Las muestras enceradas cuentan como núcleo: se sacaron para ensayo pero son núcleo recuperado, y así las mide nuestra etiqueta de Nevada (la cera dice 5.0' a 5.4'). La primera corrida las quitaba y el TCR de Nevada empeoró de 4.3 a 23.5 puntos de error.

Lo que enseñó la API real en Nevada (fila 2, donde "stone" no devuelve nada):

| Prueba | Resultado |
|---|---|
| Spark sobre la fila entera (2500 x 278, 9 a 1) | Las cajas se corren y llama núcleo a la tarjeta amarilla. No sirve |
| Spark en 4 mosaicos de unos 2.5 a 1, con 15 % de traslape | Cajas sobre las piezas, tarjetas, muestras enceradas y bloque bien clasificados |
| Unir las cajas de los mosaicos | Solo se unen las dos mitades de un objeto que corta el borde; si dos mosaicos ven el mismo objeto, queda la caja más grande. Unir todo lo que se traslapa juntaba tres piezas en una |
| SAM con la caja de una pieza | A veces la máscara sigue hasta la pieza siguiente (caja 1788 a 2078, máscara hasta 2349). Se recorta la máscara a su caja, con 5 % de margen |
| Resultado en la fila 2 | 5 piezas de núcleo (5.7, 8.6, 7.8, 7.6 y 3.3 cm) más las dos muestras enceradas; tarjeta y bloque fuera de la longitud |

Tiempo: Spark tarda de 5 a 35 s por fila (los mosaicos van en paralelo) y SAM con cajas de 5 a 13 s. Las respuestas quedan en caché (`data/cache/locate`).

## C: SAM con un toque en la revisión (28 oct)

`review.sam_point_mask` manda a SAM 3.1 la fila tocada con los puntos del geólogo (`<|point;...|>`, el negativo con `-`) y mide la pieza con las columnas de la máscara, no con su caja. `review.sam_piece` hace de esa máscara una pieza del tramo: las roturas dentro desaparecen y sus bordes se vuelven roturas (se pegan a una rotura existente si quedan a menos de 1 cm). `geometry.py` recalcula. La corrección queda con fuente `sam-point` en el historial y en `corrections.csv`.

Prueba con la API real en Nevada, tramo 2, fila 2: "stone" deja una pieza de 27 cm (38.8 a 66.0). Tres toques dan 38.8 a 47.2, 47.2 a 55.2 y 55.2 a 62.7 cm, en 2.5 a 4.8 s cada uno, los mismos bordes que Spark y SAM encontraron en B. El RQD del tramo baja de 38.6 a 21.1 (nuestra etiqueta: 15.9), como con Split, que se queda de respaldo.
