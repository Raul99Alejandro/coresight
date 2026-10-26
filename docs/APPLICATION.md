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
| 5 | UI de revisión: el geólogo corrige intervalos, las correcciones se guardan para evaluación y futuro fine-tuning, export a CSV | FastAPI (día 7) | 7 |
| 6 | Handoffs con aprobación humana: borrador de solicitud de ensayes para el laboratorio y alerta de condición de terreno para seguridad cuando la roca es mala | `pipeline.draft_handoffs` | 8 |
| 7 | Evaluación del RQD automático contra cajas logueadas a mano | `data/labels/`, sección Evaluation del README | 9 |
| 8 | Muse Code acelera el desarrollo | Ver abajo | 1 a 10 |

## Muse Code
La aplicación dice que Muse Code acelera el build. Hay que usarlo de verdad y dejar evidencia:
- Usarlo en al menos una pieza real (candidatos: calibración OpenCV o la UI de revisión).
- Anotar en este archivo qué se hizo con Muse Code y en qué commits.
- Mencionarlo en el README y en el video.

Registro de uso:
- (vacío)

## Visión (no es compromiso del hackathon)
CoreSight es el primer módulo de una capa de agentes que conecte los departamentos de una mina (operaciones, laboratorio, seguridad, administración y finanzas). Va en el pitch y en el video, no en el alcance.
