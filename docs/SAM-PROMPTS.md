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

Pendiente para B y C: el constructor de prompts en `meta_client.py` (validar `w` y `h`, máximo 16 objetos, coordenadas dentro de la imagen), con tests nuestros y hecho con Muse Code, como dice `docs/ANALISIS-2.md` sección 8.
