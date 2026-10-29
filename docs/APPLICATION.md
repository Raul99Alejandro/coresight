# Compromisos de la aplicación

Lo que se prometió en la aplicación aprobada (Cerebral Valley, aprobada el 25 oct 2026).
Track **Startup**, tema **Push the Frontier**. El track se puede cambiar en cualquier momento, pero la aplicación ya lo dice así.

La entrega final tiene que mostrar cada punto. Si algo se recorta, que sea consciente y quede escrito aquí.

| # | Compromiso | Dónde vive | Día |
|---|---|---|---|
| 1 | Calibración: bordes de la caja y marcadores de escala, px a cm | `pipeline.calibrate` | 3 |
| 2 | SAM 3.1 segmenta cada fila, cada pieza intacta y cada fractura | `pipeline.segment`, `meta_client.segment_row` | 4 |
| 3 | Motor geométrico determinista: longitudes, RQD, frecuencia de fracturas, recuperación por intervalo, cada número trazable | `geometry.py` | 0 y 5 |
| 4 | Muse Spark describe litología, alteración y mineralización con vocabulario estándar y marca anomalías (baja recuperación, fracturamiento intenso, sulfuros visibles) con explicación | `pipeline.describe`, `meta_client.describe_interval`, `schemas.GeologyDescription` | 6 |
| 5 | UI de revisión: el geólogo corrige intervalos, las correcciones se guardan para evaluación y futuro fine-tuning, export a CSV | `coresight.api`, `coresight.review`, `src/coresight/web/index.html` | 7 |
| 6 | Handoffs con aprobación humana: borrador de solicitud de ensayes para el laboratorio y alerta de condición de terreno para seguridad cuando la roca es mala | `pipeline.draft_handoffs` | 8 |
| 7 | Evaluación del RQD automático contra cajas logueadas a mano | `data/labels/`, sección Evaluation del README | 9 |
| 8 | Muse Code acelera el desarrollo | Ver abajo | 1 a 10 |

## Muse Code
La aplicación dice que Muse Code acelera el build. Hay que usarlo de verdad y dejar evidencia:
- Usarlo en al menos una pieza real (candidatos: calibración OpenCV o la UI de revisión).
- Anotar en este archivo qué se hizo con Muse Code y en qué commits.
- Mencionarlo en el README y en el video.

Registro de uso:
- 27 oct, día 8: Muse Code 1.4.13 escribió `src/coresight/verify.py` (el verificador determinista de los borradores de los agentes de área).
  - La especificación son los 20 tests de `tests/test_verify.py`, escritos antes por nosotros. La implementación es de Muse Code y no la editamos.
  - Ronda 1, sesión `bbc6432a-3cb8-407d-8572-921d33527e31`: el verificador completo contra 15 tests. 28 llamadas al modelo.
  - Ronda 2, sesión `88fc39bc-b75a-47b0-8d5f-466e68048e0a`: arreglo de ruff y 5 tests nuevos (presupuesto restante, historial del pozo, runs desde uno). 15 llamadas.
  - Comando: `muse exec --contributor-mode off --disable-approval --json`, con sandbox.
  - La sandbox de Windows de Muse no pudo arrancar PowerShell, así que corrimos pytest y ruff fuera de ella y le regresamos el resultado.
  - Trazas: `docs/muse-code/verify-1.json` y `verify-2.json`. Commit: `0b594f1`.
  - El campo `"model": "muse-spark-1.3-contributor"` de esas dos trazas es el id de modelo que Muse Code usa por omisión en esta cuenta, no el modo contributor (que iba apagado). Lo confirmamos con `muse model-profile show` y dos corridas de prueba. Desde el día 10 todas las corridas llevan `--model muse-spark-1.3`.
- 27 oct, día 10 (punto A del segundo análisis): dos corridas más, mismo método, con `--model muse-spark-1.3`.
  - `src/coresight/gate.py`, la compuerta de entrada: rechaza una foto que no es caja con la confianza de calibración, la de SAM y el `is_core_tray` de Muse Spark. Especificación: 16 tests de `tests/test_gate.py`, escritos antes por nosotros. Sesión `01a17f99-8f2a-7be0-9d5a-d4e1efe7b717`, 14 llamadas. Traza: `docs/muse-code/gate-1.json`. Commit: `413093d`.
  - `src/coresight/verify.py`, ronda 3: tramos desde 1 y detalles en palabras, sin nombres de campo. Sesión `01a17f99-9b2b-7bd3-91e8-c08bf9dd5502`, 22 llamadas. Traza: `docs/muse-code/verify-3.json`. Commit: `1d1681b`.
  - La sandbox sigue sin arrancar PowerShell; corrimos pytest y ruff fuera. No editamos su código.
- 28 oct (puntos B y C del segundo análisis): Muse Code 1.4.14, mismo método, `--model muse-spark-1.3`.
  - `sam_prompt` y `grid_box_to_pixels` en `src/coresight/meta_client.py`: el constructor de prompts de caja y punto de SAM 3.1 y el paso de la cuadrícula 0 a 1000 de Spark a pixeles. Especificación: 22 tests de `tests/test_sam_prompts.py`, escritos antes por nosotros (commit `76b9cf1`). Sesión `01a17fc6-f402-7be3-981a-3577dbf7c4c5`, 17 llamadas. Traza: `docs/muse-code/sam-prompts-1.json`. Commit: `84b06fe`.
  - La sandbox sigue sin PowerShell: Muse Code revisó los tests a mano y nosotros los corrimos (39 en verde, ruff limpio). Su herramienta de edición no encontraba el texto en el archivo con CRLF y lo reescribió con LF; git lo normaliza y solo cambiaron las dos funciones y tres ayudantes.
- 28 oct (punto D del segundo análisis): la agregación del barreno por profundidad, `pieces_at_depth` y `log_hole` en `src/coresight/geometry.py`. Muse Code 1.4.14, `--model muse-spark-1.3`. Primera pieza con constructor y revisor, como recomendó Agents 102.
  - Especificación: `tests/test_hole.py`, escrita antes por nosotros (commit `c780b8d`, 29 tests).
  - Constructor, ronda 1: sesión `01a183d3-a60a-74c3-b5ab-dd720838a11d`, 15 llamadas. Traza: `docs/muse-code/hole-1.json`. Commit: `895b4ba`.
  - Revisor de solo lectura (`--disable-write`, sandbox encendida): sesión `01a183db-f694-7060-b8de-67eb8f826b4e`, 5 llamadas. Traza: `docs/muse-code/hole-review-1.json`. Encontró errores reales que los tests no veían: una rotura natural justo en el límite de un intervalo de 1 m se perdía, una caja dentro de otra daba un hueco falso, las astillas al borde de un tramo perdían núcleo, dos tramos traslapados de la misma caja pasaban sin aviso y la tolerancia de 1 cm se aplicaba de dos formas. Dos hallazgos eran decisiones de diseño ya escritas (un tramo que sigue en una caja que falta se registra hasta el borde de la caja, igual que en la caja; un traslape de hasta 1 cm se recorta).
  - Al escribir los tests nuevos encontramos uno más: el fin de un tramo dentro de un intervalo contaba como fractura en el intervalo y no en el tramo.
  - Los arreglos no los hicimos a mano: 13 tests nuevos (commit `f9b33d3`) y una segunda ronda del constructor, sesión `01a183e5-86e3-7391-89d7-257f02ae3408`, 23 llamadas. Traza: `docs/muse-code/hole-2.json`. Commit: `7d90982`. Ahora las fracturas y el núcleo suman lo mismo por tramo y por intervalo.
  - Segundo revisor de solo lectura sobre la ronda 2: sesión `01a183ee-17c2-7872-965a-26e7a5a56b8d`, 6 llamadas. Traza: `docs/muse-code/hole-review-2.json`. Encontró cuatro errores reales más (dos tramos de la misma caja traslapados por redondeo tronaban, un hueco dentro de una caja daba un intervalo con RQD 0, el núcleo perdido entre piezas reunidas contaba como núcleo y una rotura en un límite de punto flotante como `3 * 0.3` caía un intervalo abajo). Uno estaba en nuestra propia clase `DepthPiece` y lo arreglamos nosotros con test. Quedan como decisión escrita: un tramo partido entre dos cajas cuenta la partición como fractura (el geólogo la marca mecánica en la revisión si se rompió para caber en la caja), y una caja dentro del hueco interno de otra es un límite conocido.
  - 4 tests nuevos (commit `b715f11`) y tercera ronda del constructor: sesión `01a183f8-64f7-76f3-9315-8faf5fe87a2d`, 20 llamadas. Traza: `docs/muse-code/hole-3.json`.
  - En total: 3 rondas del constructor y 2 del revisor, 69 llamadas. La sandbox sigue sin PowerShell; corrimos pytest y ruff fuera (320 en verde, ruff limpio). No editamos su código.

- 28 oct (punto E del segundo análisis): la verificación en los hitos, `check_finding` y `check_routing` en `src/coresight/verify.py`, y `verify(..., trends)`. Muse Code 1.4.14, `--model muse-spark-1.3`, constructor y revisor como en D.
  - Especificación: `tests/test_verify_milestones.py`, escrita antes por nosotros (commit `2e02cd2`, 23 tests). Las tendencias entre cajas (`hole.hole_trends`) y el agente de barreno los escribimos nosotros.
  - Constructor, ronda 1: sesión `01a18410-fb19-7921-aa89-a7f0aa93faa8`, 32 llamadas. Traza: `docs/muse-code/routing-1.json`. Commit: `5653d4d`.
  - Revisor de solo lectura (`--disable-write`): sesión `01a1841c-df12-7a23-a050-4a64d149e9f2`, 21 llamadas. Traza: `docs/muse-code/routing-review-1.json`. Encontró dos errores reales (un signo menos se perdía y "-2" pasaba como "2"; un porcentaje escrito con palabras pasaba como profundidad) y dos detalles (las tendencias desconocidas en una sola frase; finanzas pasaba sin ruta de laboratorio). Los cuatro volvieron como 6 tests nuevos (commit `1539361`); no los arreglamos a mano.
  - Constructor, ronda 2: sesión `01a18424-7509-7df0-9a12-996019274166`, 33 llamadas. Traza: `docs/muse-code/routing-2.json`. Los 29 tests de hitos y los 20 de `verify` en verde.
  - En total: 2 rondas del constructor y 1 del revisor, 86 llamadas. La sandbox sigue sin PowerShell; corrimos pytest y ruff fuera (383 en verde, ruff limpio). No editamos su código.
  - Prueba real en local con la API de Meta (Nevada U12G caja 3, con la caja 1 aprobada): el código encontró 3 tendencias, el agente de barreno propuso avisar a geotecnia (3 de 3 checks, el juez respaldó 10 de 10 afirmaciones), Wonder mandó solo a seguridad (4 de 4 áreas coherentes al primer intento) y el borrador de seguridad pasó 4 de 4 checks y 11 de 11 afirmaciones. Unos 110 s, la mitad verificando.

- 28 oct (punto F del segundo análisis): el ciclo de aprendizaje, `mae_of`, `fit`, `leave_one_box_out` y `learning_curve` en `src/coresight/learning.py`. Muse Code 1.4.14, `--model muse-spark-1.3`, constructor y revisor como en D y E.
  - Especificación: `tests/test_learning.py`, escrita antes por nosotros (commit `85f6a1c`, 18 tests).
  - Constructor, ronda 1: sesión `01a18464-3527-7f22-a9b6-2c50b9baa9a7`, 15 llamadas. Traza: `docs/muse-code/learning-1.json`. Commit: `d718864`.
  - Revisor de solo lectura (`--disable-write`): sesión `01a18468-a270-7d61-8d57-23efb2b49741`, 11 llamadas. Traza: `docs/muse-code/learning-review-1.json`. En `learning.py`: duplicados que ganaba el último, un NaN en un candidato no usado que pasaba, ningún candidato elegible que regresaba el valor por omisión sin medirlo y un tramo repetido que pesaba doble. Volvieron como 5 tests (commit `ee530fb`). En nuestro script encontró dos errores reales: las cajas 5 y 6 de Onkalo son una sola foto (dejar una caja fuera no deja fuera su foto) y el eje del total contaba tramos por sitio. Los arreglamos nosotros: la validación cruzada ahora es por foto.
  - Constructor, ronda 2: sesión `01a1846d-5cd8-7fd3-9770-6ad32a239c2d`, 14 llamadas. Traza: `docs/muse-code/learning-2.json`. 23 de 23 en verde.
  - En total: 2 rondas del constructor y 1 del revisor, 40 llamadas. La sandbox sigue sin PowerShell; corrimos pytest y ruff fuera (440 en verde, ruff limpio). No editamos su código.
  - Resultado medido (`outputs/eval/learning.md`): desde los umbrales por omisión, Nevada fuera de muestra queda en 15.1 puntos (no había nada que aprender); desde un sitio mal ajustado baja de 21.6 a 16.6 con las correcciones de la otra foto. Queda como "listo para aprender", sin presumir mejora. Las correcciones de descripción entran como few-shot a Spark y Glimmer; sin descripciones de un geólogo públicas para medir, no se presume.

- 30 oct (punto 7 del tercer análisis): `check_role` en `src/coresight/verify.py`, la regla determinista que impide que un borrador le diga a la operación que pare ("Do not continue drilling until..."), y su llamada en `verify` y `check_finding`. Muse Code 1.4.14, `--model muse-spark-1.3`, constructor y revisor como en D, E y F.
  - Especificación: `tests/test_verify_role.py`, escrita antes por nosotros (commit `3252a1d`, 32 tests). La lista cerrada de acciones (`schemas.DraftAction`) y la instrucción al juez las escribimos nosotros.
  - Constructor, ronda 1: sesión `01a1854c-adb6-7981-b7b3-367fe18b3b11`, 18 llamadas. Traza: `docs/muse-code/role-1.json`. Commit: `8093263`.
  - Revisor de solo lectura (`--disable-write`): sesión `01a1855a-ec2a-7611-bdd1-412fd2b23ce8`, 4 llamadas. Traza: `docs/muse-code/role-review-1.json`. Seis errores reales: un "Stop and get geotech review." al inicio del cuerpo pasaba porque el título se pegaba sin punto; `until` solo se buscaba una vez; un salto de línea no cerraba la oración; una coincidencia podía cruzar de una oración o de un campo a otro (y rechazar "Do not mix samples. Drilling continues"); unas comillas después de dos puntos escondían la orden. Volvieron como 8 tests (commit `fa3b5de`); no los arreglamos a mano.
  - Constructor, ronda 2: sesión `01a18564-2d84-7920-bbb8-d725b6c00c7f`, 33 llamadas. Traza: `docs/muse-code/role-2.json`. 40 de 40 en verde.
  - En total: 2 rondas del constructor y 1 del revisor, 55 llamadas. La sandbox sigue sin PowerShell; corrimos pytest y ruff fuera (498 en verde, ruff limpio). No editamos su código.
  - Prueba con los textos reales de Spark: rechaza "Do not continue drilling until the safety team reviews.", "Before the next run: stop and get geotech review." y "Do not drill ahead without geotechnical review."; deja pasar "needs geotech review before further drilling" y "have a geotechnical review before the next run".

## Alcance ampliado (decidido el 26 oct)
Raúl decidió ir más allá de lo prometido: núcleo profundo más agentes que llevan el dato a otras áreas de la mina. Detalle y calendario en `docs/PLAN.md`.

| # | Compromiso nuevo | Modelo de Meta | Día |
|---|---|---|---|
| 9 | Orquestador que decide qué áreas se ven afectadas por una caja aprobada | Muse Wonder | 8 |
| 10 | 4 agentes de área con borradores y aprobación humana: laboratorio, seguridad y geotecnia, planta, finanzas | Muse Spark 1.3 con herramientas | 8 |
| 11 | Correcciones dictadas por voz en la UI de revisión (`meta_client.transcribe`) | Muse Voice Transcribe | 7 |
| 12 | Descripción con modelo abierto en infraestructura propia (modo sin internet en la mina) | Muse Glimmer, plan B Muse Spark Open | 6 |
| 13 | Evaluación científica: MAE, Bland-Altman, ablaciones, robustez, costo y tiempo por caja | Todos | 5 y 9 |
| 14 | Video con HyperFrames y voz | (herramienta de video) | 10 |

El compromiso 6 (handoffs a laboratorio y seguridad) queda cubierto por el 10.

Premios extra a los que apunta: Best Agentic Use-Case (9 y 10), Best Build on Meta Open Weight Models (12), Most Viral Project (14).

## Visión (no es compromiso del hackathon)
CoreSight es el primer módulo de una capa de agentes que conecte los departamentos de una mina. En el hackathon se construyen laboratorio, seguridad, planta y finanzas. Mantenimiento, operaciones y administración van en el pitch y en el video, no en el código.
