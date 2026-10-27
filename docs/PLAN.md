# Plan día por día

Entrega oficial: **mié 4 nov 2026, 21:00 ET = 20:00 hora de Zacatecas**. Meta interna: enviar antes de las **18:00**.
Kickoff: lun 26 oct a las 10:00 de Zacatecas (ya pasó).
Juzgado: 5 al 8 nov. Final en vivo y ganadores: lun 9 nov.

## Alcance (decidido el 26 oct)

Núcleo profundo más agentes de área, en ese orden de prioridad:

1. **Núcleo**: foto, calibración, SAM 3.1, RQD/TCR/FF deterministas, descripción con Muse Spark, revisión del geólogo, CSV.
2. **Evaluación científica** contra el RQD del geólogo (156 tapas del Kaggle con RQD y CR medidos).
3. **Orquestador con Muse Wonder** y **4 agentes de área**: laboratorio, seguridad/geotecnia, planta y finanzas. Cada uno solo genera borradores y nada sale sin aprobación humana.
4. **Voz**: el geólogo dicta correcciones con Muse Voice Transcribe.
5. **Glimmer local**: la descripción también corre con un modelo abierto en infraestructura propia (modo sin internet en la mina).

Mantenimiento y operaciones quedan como visión (en el video, no en el código). Muse Image no se usa.

## Calendario

| Día | Fecha | Objetivo | Listo cuando |
|---|---|---|---|
| 0 | dom 25 oct | Repo, plan, buscar fotos de cajas de núcleo | Hecho. Repo con tests en verde y CI; fuentes con licencia en `SOURCES.md` |
| 1 | lun 26 oct | Kickoff, API key, smoke test de SAM 3.1 y Muse Spark con 1 foto | Hecho. `scripts/smoke_day1.py` pasa contra la API real (SAM con prompt "stone", Muse Spark valida) |
| 2 | lun 26 oct | Dataset y RQD manual | Hecho adelantado (`158f8f5`). Kaggle en `data/raw/` y 13 etiquetas que validan con `BoxLabel` |
| 3 | mar 27 oct | Calibración. Pedir créditos de Baseten y Modal | Error px→cm < 2% en las cajas etiquetadas; filas recortadas correctamente; solicitudes de partners enviadas |
| 4 | mié 28 oct | Segmentación SAM 3.1 de piezas y fracturas en cm | Hecho adelantado (`897b4a5`, 26 oct). Lista de `Piece` por fila en cm; caché por hash de imagen y reintentos |
| 5 | jue 29 oct | Motor geométrico conectado y primera evaluación | Hecho adelantado (`4f41134`, `a728c9d`). De punta a punta por tramo; MAE de RQD 8.6 (9.9 sin marcas del geólogo) en 39 tramos |
| 6 | vie 30 oct | Muse Spark con descripciones y anomalías; Glimmer como segundo backend | Hecho. `pipeline.describe` da un `IntervalDescription` validado por tramo; `low_recovery` e `intense_fracturing` salen de TCR y FF (`anomalies.py`), `visible_sulfides` del modelo; Muse Spark (API) y Glimmer (llama.cpp local) con el mismo contrato; muestra en `outputs/describe/compare.md` (`scripts/describe_boxes.py`) |
| 7 | sáb 31 oct | UI de revisión con voz, export CSV, demo desplegada | Hecho adelantado (`814a154`, 27 oct). Demo en https://coresight.analizac.com. API FastAPI (`coresight.api`) y página de revisión (`src/coresight/web/`); correcciones de roturas, piezas y descripción, escritas o dictadas con Muse Voice Transcribe, guardadas junto al valor original (`coresight.review`); RQD/TCR/FF recalculados solo por `geometry.py`; CSV del registro y de las correcciones; errores visibles; despliegue en `docs/DEPLOY.md` |
| 8 | dom 1 nov (arranca 27 oct) | Evidencia pública, muestra dramática, orquestador y 4 agentes con autonomía verificable, Muse Code | Ver "Cambios por el análisis": puntos 1 a 4 (y 5 si la API acepta prompts de punto). Al aprobar una caja, el orquestador decide qué áreas aplican y por qué; los agentes usan herramientas; un verificador determinista revisa cada borrador; registro de decisiones visible; cada borrador con su botón de aprobar; nada se envía solo |
| 9 | lun 2 nov | Evaluación científica completa, procedencia de modelos abiertos, números de impacto | Puntos 6 a 8. Tabla en el README: cifra principal sin marcas del geólogo con intervalo de confianza, Bland-Altman, ablaciones, robustez seco/mojado, comparación con la variación entre geólogos, calidad de descripciones, costo y tiempo por caja, casos de falla con foto |
| 10 | mar 3 nov | Video con HyperFrames y voz, README final, portada y prueba de abuso | Puntos 9, 10 y 12. Video de 3 min en inglés con subtítulos, que abre con la línea de trabajo previo y sigue el guion de `docs/ANALISIS.md` (sección 4); README con lo hecho antes y durante el hackathon |
| 11 | mié 4 nov | Colchón y envío | Enviado antes de las 18:00 con repo público, video y demo; marcar los premios Open Weights, Agentic y Viral; borrador del post en X para que Raúl lo publique |

## Agentes de área (día 8)

| Agente | Disparador | Borrador que genera | Dato que usa |
|---|---|---|---|
| Laboratorio | Intervalo con sulfuros visibles o alteración fuerte | Solicitud de ensayes con intervalos y prioridad | Descripción de Muse Spark y profundidades |
| Seguridad y geotecnia | RQD en clase poor o very poor, o fracturamiento intenso | Alerta de condición de terreno con la clase de Deere | RQD y FF de `geometry.py` |
| Planta | Cambio de litología o de sulfuros respecto a la caja anterior | Aviso del tipo de mineral que viene para el plan de proceso | Litología, alteración y mineralización |
| Finanzas | Cualquier solicitud de ensayes | Costo estimado del ensaye y su efecto en el presupuesto del barreno | Tabla de precios configurable (de ejemplo, marcada como tal; nunca precios inventados como reales) |

El orquestador (Muse Wonder) decide qué agentes aplican y les pasa la caja aprobada. Los agentes corren con Muse Spark y herramientas. Los números siempre vienen de `geometry.py`.

## Evaluación científica (días 5 y 9)

- Verdad de terreno: RQD y CR por tramo de las tapas del Kaggle (geólogo de la mina) y las etiquetas propias.
- Métricas: MAE y sesgo de RQD y TCR, Bland-Altman, exactitud de la clase de Deere, error px→cm.
- Ablaciones: solo SAM contra SAM más reglas geotécnicas; prompts de SAM; con y sin el plan B de perfil de intensidad.
- Robustez: Onkalo 1 (seca) contra Onkalo 2 (mojada), mismas cajas.
- Descripciones: Muse Spark contra Glimmer, revisadas por Raúl en una muestra.
- Operación: costo y tiempo por caja.
- Los datos NC (Kaggle) solo para evaluación, nunca en la demo desplegada.

## Riesgos y plan B

| Riesgo | Plan B |
|---|---|
| Sin datos reales | Imágenes públicas y etiquetar 10 cajas a mano |
| SAM no separa fracturas finas | Detectar cortes por perfil de intensidad a lo largo del eje del núcleo |
| Límites de la API | Caché por hash de imagen (`data/cache/`) y reintentos con backoff |
| Falta de tiempo | Recortar en este orden: ciclo de aprendizaje (11), SAM con clic (5), clip y post (12), agente de finanzas, agente de planta. Nunca el núcleo, la evaluación, la muestra dramática (1), la evidencia pública (2) ni los agentes verificables (4) |
| Muse Wonder no rinde como orquestador o no está disponible por API | Orquestar con Muse Spark 1.3 y tool calling |
| Glimmer no corre en el hardware disponible | Muse Spark Open en Baseten o Modal (también cuenta para el premio de modelos abiertos) |
| Muse Voice Transcribe falla con español o ruido | Dictado opcional; la corrección escrita siempre funciona |
| Créditos de Meta tardan | Las llamadas se cobran a la tarjeta; vigilar el saldo en Billing |
| Reglas oficiales piden algo no previsto (duración de video, repo público, formato) | Leerlas el día 1 y ajustar este plan ese mismo día |
| Muse Spark o SAM 3.1 con restricción regional o de cuota desde México | Probar el día 1; si falla, preguntar en Discord y usar créditos de partners (Baseten, Modal, Fireworks) con modelos open-weights |

## Ajustes por la investigación (25 oct)
Lo que dicen la página oficial y la aplicación, y cómo cambia el plan:

- **CI reactivado (26 oct).** Las reglas piden repo público; al hacerlo público Actions es gratis y el workflow vuelve a correr en cada push y PR.
- **Trabajo previo marcado.** Lo hecho el 25 oct (antes del kickoff) está listado en la sección "Built before the hackathon" del README. Todo lo posterior a `013503a` es del hackathon.
- **Track Startup se juzga por "technical execution" y "whether it holds up in production".** Por eso se agregó: CI con tests y ruff desde el día 0, caché y reintentos en `meta_client` (día 4), demo desplegada con URL pública (día 8), manejo de errores visible en la UI (fotos malas, caja sin escala).
- **Final en vivo el 9 nov.** Tener la demo desplegada estable después de la entrega y un guion de 3 minutos ensayado.
- **Reglas oficiales leídas (26 oct).** Repo público, video de 3 minutos que muestre solo lo hecho en el hackathon, se permite código previo si se marca claramente, entrega en la plataforma de Cerebral Valley. Evitar parecer un "simple image analyzer": el flujo completo con revisión y agentes es lo que lo distingue.
- **Muse Code está prometido en la aplicación.** Usarlo en al menos una pieza real y documentarlo en `docs/APPLICATION.md`.
- **Modo Contributor de Muse Spark** es más barato pero Meta puede entrenar con esos datos. Solo usarlo con imágenes públicas, nunca con datos de clientes.
- **Créditos de Meta aplicados (26 oct): $150.** Mientras se usan, Billing avisa que el contenido puede usarse para mejorar el producto. Misma regla: solo imágenes públicas, nunca fotos de una mina o de un cliente. Para datos privados, "Stop using free credits" en Billing o el modo Glimmer local.
- **Workshops y office hours en Discord** del 27 oct al 4 nov. Llevar preguntas concretas de SAM 3.1 (prompts para fracturas) a las office hours.

## Cambios por el análisis (27 oct)

Adoptados de `docs/ANALISIS.md`. La nota estimada sube de 6.5 a unos 8.5.

| # | Cambio | Día |
|---|---|---|
| 1 | Muestra dramática como primera muestra de la demo: roca mala y sulfuros visibles, de Commons con licencia libre o, mejor, una caja real de una mina de Zacatecas con permiso. Una foto privada de mina nunca pasa por los créditos gratis de Meta: se procesa con Glimmer local o con los créditos gratis apagados | 8 |
| 2 | Evidencia pública: métricas de `outputs/eval/` y `outputs/describe/` en el repo (sin fotos del Kaggle), README sin "Early scaffold" y con Evaluation llena, `LICENSE` | 8 |
| 3 | Muse Code de verdad en al menos un agente o el verificador, con capturas y commits listados en `APPLICATION.md` y el README | 8 |
| 4 | Agentes con autonomía verificable: Muse Wonder decide qué áreas aplican y por qué (plan B Spark 1.3); agentes con herramientas (`geometry.py`, tabla de precios de ejemplo, historial); verificador determinista de cada borrador; registro de decisiones en la UI; citar la Agents Rule of Two. Ver Agents 101 y 102 antes de construir | 8 |
| 5 | SAM 3.1 con prompt de punto en la revisión (clic en una pieza y se vuelve a segmentar), si la API lo acepta | 8 o colchón |
| 6 | Manifiesto de procedencia de Glimmer y Spark Open en el repo y clip de Glimmer sin red | 9 |
| 7 | Evaluación honesta: cifra principal sin marcas, intervalo de confianza, Bland-Altman, variación entre geólogos | 9 |
| 8 | Números de impacto con fuente y, si se puede, 15 s de un geólogo real (Raúl consigue el contacto) | 9 |
| 9 | Portada con imagen de una caja y encabezado de móvil arreglado | 10 |
| 10 | Prueba de abuso (foto que no es caja, foto enorme, caja sin escala), caché precalentada y vigilancia de créditos | 10 |
| 11 | Cerrar el ciclo: few-shot o LoRA de Glimmer con las correcciones del geólogo, medido antes y después. Solo si 1 a 10 están hechos | Colchón |
| 12 | Clip vertical y borradores del post en X y del mensaje de Community Vote (Raúl los publica) | 10 |

Lo que no cambia: la arquitectura neurosimbólica, el track Startups, las 4 áreas, los 3 backends de descripción, la revisión humana obligatoria, el diseño visual y el día 10 completo para el video.
El video no presume `geometry.py` (es trabajo previo del 25 oct) y abre con la línea de qué era previo.
