# CoreSight

Registro automático de núcleos de barrenación a partir de fotos de cajas de núcleo.
Proyecto de AnaliZac para el Meta Global AI Developer Hackathon.

- Track: **Startup** (se juzga ejecución técnica y que aguante en producción).
- Tema: **Push the Frontier** (modelos de Meta conectados al mundo físico).
- Entrega: **mié 4 nov 2026, 20:00 hora de Zacatecas** (21:00 ET). Meta interna: 18:00.
- Juzgado: 4 al 8 nov. Final en vivo y ganadores: lun 9 nov.
- Plan día por día: `docs/PLAN.md`. Lo prometido en la aplicación: `docs/APPLICATION.md`.
- Comando `/day`: dice qué toca hoy y propone tareas.

Entrada: foto de una caja. Salida: registro geotécnico y geológico por intervalo, revisado por un geólogo.

## Restricción
Nada relacionado con Freight Technologies: ni código, ni datos, ni el dominio de logística o aduanas.

## Arquitectura (neurosimbólica)

| # | Etapa | Dónde | Tecnología |
|---|---|---|---|
| 1 | calibration: bordes de caja, marcadores de escala, px a cm, separar filas | `pipeline.calibrate` | OpenCV |
| 2 | segmentation: piezas intactas y fracturas por fila | `pipeline.segment` + `meta_client` | SAM 3.1 (Meta Model API) |
| 3 | geometry: longitudes, RQD, frecuencia de fracturas, recuperación | `geometry.py` | Python determinista, sin LLM |
| 4 | describe: litología, alteración, mineralización, anomalías | `pipeline.describe` + `meta_client` | Muse Spark, salida validada con Pydantic |
| 5 | api + UI de revisión, correcciones escritas o dictadas, export CSV | por crear (día 7) | FastAPI, Muse Voice Transcribe |
| 6 | agentes de área: orquestador y borradores para laboratorio, seguridad/geotecnia, planta y finanzas | `pipeline.draft_handoffs` (día 8) | Muse Wonder orquesta, Muse Spark con herramientas; solo con aprobación humana |

La etapa 4 también corre con Muse Glimmer en infraestructura propia (modo sin internet), con el mismo contrato de salida.
Visión a futuro (no es compromiso del hackathon): sumar mantenimiento, operaciones y administración a la misma capa de agentes.

## Reglas
- Los cálculos geotécnicos viven solo en `geometry.py` y tienen tests. El LLM nunca calcula el RQD.
- Toda salida de modelo se valida con Pydantic (`schemas.py`) antes de usarse.
- Las llamadas a Meta Model API van solo en `meta_client.py`. No inventar endpoints ni IDs de modelo: llenar los TODO con la documentación oficial (https://dev.meta.ai/docs/) y probarlos con la API key real.
- Los secretos van en `.env`, nunca en git.
- Ningún handoff se envía sin aprobación humana. Solo se generan borradores.
- Las imágenes públicas usadas en el dataset se registran con fuente y licencia en `data/labels/SOURCES.md`.

## Definiciones geotécnicas
- **Tramo (run)**: intervalo de barrenación de `from_m` a `to_m`. Las posiciones de piezas van en cm desde el inicio del tramo.
- **RQD** (Rock Quality Designation, Deere): suma de piezas intactas >= 10 cm / longitud del tramo × 100.
- **TCR** (Total Core Recovery): núcleo recuperado / longitud del tramo × 100.
- **Fractura natural**: rotura que existía en la roca. Fracturas = piezas intactas - 1. Frecuencia = fracturas / metro.
- **Rotura mecánica**: la hizo la perforación o el manejo. Las piezas a ambos lados se vuelven a unir porque estaban intactas in situ.
- **Rotura dudosa (uncertain)**: se trata como natural (criterio conservador) y se cuenta para revisión del geólogo.
- **Clase de Deere**: <25 very poor, <50 poor, <75 fair, <90 good, si no excellent.

## Comandos (PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check .
```
