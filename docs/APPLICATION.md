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
  - Trazas: `docs/muse-code/verify-1.json` y `verify-2.json`. Commit: pendiente.

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
