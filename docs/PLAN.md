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
| 4 | mié 28 oct | Segmentación SAM 3.1 de piezas y fracturas en cm | Lista de `Piece` por fila en cm para las cajas etiquetadas; caché por hash de imagen y reintentos |
| 5 | jue 29 oct | Motor geométrico conectado y primera evaluación | Una foto produce RQD, TCR y FF por intervalo de punta a punta; MAE preliminar en las 13 etiquetas |
| 6 | vie 30 oct | Muse Spark con descripciones y anomalías; Glimmer como segundo backend | Hecho. `pipeline.describe` da un `IntervalDescription` validado por tramo; `low_recovery` e `intense_fracturing` salen de TCR y FF (`anomalies.py`), `visible_sulfides` del modelo; Muse Spark (API) y Glimmer (llama.cpp local) con el mismo contrato; muestra en `outputs/describe/compare.md` (`scripts/describe_boxes.py`) |
| 7 | sáb 31 oct | UI de revisión con voz, export CSV, demo desplegada | El geólogo corrige un intervalo escribiendo o dictando; la corrección se guarda; el CSV se descarga; URL pública |
| 8 | dom 1 nov | Orquestador Muse Wonder y 4 agentes de área | Al aprobar una caja se generan borradores de laboratorio, seguridad, planta y finanzas, cada uno con su botón de aprobar; nada se envía solo |
| 9 | lun 2 nov | Evaluación científica completa | Tabla en el README: MAE de RQD y TCR, Bland-Altman, ablaciones, robustez seco/mojado, calidad de descripciones, costo y tiempo por caja, casos de falla |
| 10 | mar 3 nov | Video con HyperFrames y voz, README final | Video de 3 min o menos con capturas reales de la demo y la evaluación; README con lo hecho antes y durante el hackathon |
| 11 | mié 4 nov | Colchón y envío | Enviado antes de las 18:00 con repo público, video y demo; post en X para el premio viral |

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
| Falta de tiempo | Recortar en este orden: agente de finanzas, agente de planta, Glimmer, voz. Nunca el núcleo ni la evaluación |
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
