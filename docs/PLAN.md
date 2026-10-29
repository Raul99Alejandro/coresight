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
| 8 | dom 1 nov (arranca 27 oct) | Evidencia pública, muestra dramática, orquestador y 4 agentes con autonomía verificable, Muse Code | Hecho adelantado (`0b594f1`, `91d05f6`, `c21a397`, 27 oct). Puntos 1 a 4 de "Cambios por el análisis": orquestador con Muse Wonder, 4 agentes con herramientas, `verify.py` escrito con Muse Code, registro de decisiones, aprobación por borrador; muestra Nevada U12G; botón para partir piezas. El punto 5 pasa a C del segundo análisis |
| 9 | lun 2 nov | Evaluación científica completa, procedencia de modelos abiertos, números de impacto | Hecho adelantado (27 oct). Cifra principal contra el geólogo de la mina, sin marcas: MAE de RQD 11.2 [IC 95% 6.1 a 18.9] en 34 tramos; Bland-Altman, clase de Deere, ablaciones, Onkalo seca contra mojada, casos de falla con foto pública (`outputs/eval/`, `evaluation.py`); procedencia de Glimmer con hashes iguales a los de Hugging Face (`docs/PROVENANCE.md`) y guion del clip sin red (`docs/CLIP_GLIMMER.md`); números de impacto con fuente (`docs/IMPACT.md`). Pendiente: grabar el clip, revisión de Raúl de una muestra de descripciones, geólogo real |
| 10 | mar 3 nov | Video con HyperFrames y voz, README final, portada y prueba de abuso | Puntos 9, 10 y 12 (la portada y la prueba de abuso se adelantan a A y G del segundo análisis). Video de 3 min en inglés con subtítulos, que abre con la línea de trabajo previo y sigue el guion de `docs/ANALISIS-2.md` (sección 7); README con lo hecho antes y durante el hackathon |
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
| Falta de tiempo | Recortar en este orden (segundo análisis): SAM local (I), ciclo de aprendizaje (F), agente de barreno (E, dejar solo el orquestador sin reglas fijas), vista de barreno sin 3D (D). Nunca el núcleo, la evaluación, la compuerta de entrada (A), Spark localiza y SAM corta (B) ni SAM con clic (C) |
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

## Plan revisado por el segundo análisis (27 oct, noche)

Adoptado de `docs/ANALISIS-2.md`. Nota estimada: 6.8 hoy, 8.2 a 8.6 con este plan.
La idea: pasar de una foto a un barreno, con los modelos de Meta encadenados y corrigiéndose, y que el sistema diga "no" cuando no debe medir.

| Fecha | Punto | Objetivo | Listo cuando |
|---|---|---|---|
| lun 27 oct, noche | A | Desplegar días 8 y 9; crédito de foto por muestra; tramos desde 1 y sin nombres de campo en los textos de agentes | La URL pública muestra Nevada y agentes |
| mar 28 oct | A | Compuerta de entrada (confianza de calibración, confianza de SAM y `is_core_tray` de Spark validado con Pydantic), campo de filas al subir, diálogo de aprobar que no se queda abierto. Ver Agents 102 a las 10:00. Probar cajas y puntos de SAM con la API real (foto pública) | Una web, una selfie y una caja sin escala dan error claro, con test. Smoke test de SAM con caja y con punto |
| mié 29 oct | B y C | Spark localiza filas y lo que no es núcleo, SAM corta con esas cajas; el geólogo toca la foto y SAM vuelve a cortar con punto positivo o negativo (Split queda de respaldo) | Ablación `spark+sam` en `outputs/eval`; el clic en Nevada tramo 2 corrige como hoy Split |
| jue 30 oct | D | Vista de barreno: columna continua por profundidad y 3D simple (traza de ejemplo marcada como tal) con Onkalo 5+6 y U12G 1+3. Agregación en `geometry.py` con tests. Taller de Fireworks 10:00 | Columna y 3D en la app |
| vie 31 oct | E | Agente de barreno con tendencias entre cajas; orquestador sin reglas fijas en el prompt; progreso legible, sin JSON. Lo de Agents 102 (`docs/AGENTS102.md`): verificar el ruteo de Wonder como hito antes de redactar; LLM como juez (Muse Spark, Pydantic) después de `verify.py` que revisa cada afirmación de texto contra la descripción aprobada y nunca aprueba lo que `verify.py` rechazó; hasta 3 intentos con retroalimentación y luego escalar a la persona con el motivo; turnos, intentos y tiempo de verificación en el registro | Una caja aprobada dispara una alerta de tendencia verificada en dos capas; un borrador que falla 3 veces llega a la persona marcado |
| sáb 1 nov | F, G, H | Ciclo de aprendizaje medido (timebox 6 h, sin LoRA), portada con imagen y recorrido de 60 s, prueba de abuso completa, caché precalentada, desplegar. Cierre de la caja real y el geólogo | Gráfica antes y después o nota honesta; portada nueva en producción. G y F hechos adelantados el 28 oct (`9ea15cb` en producción; F en `outputs/eval/learning.md`: sin mejora desde el valor por omisión, 21.6 a 16.6 desde un sitio mal ajustado; listo para aprender). H sigue en manos de Raúl |
| dom 2 nov | | Congelar código. Ensayar 3 veces. Grabar clip de Glimmer sin red y tomas de la demo | Nada nuevo entra |
| lun 3 nov | | Día 10: video y README final | Video de 3 min exportado |
| mar 4 nov | | Día 11: envío antes de las 18:00 | Enviado |

Muse Code en tres piezas nuevas, con tests escritos antes por nosotros y trazas en `docs/muse-code/`: la regla de la compuerta (A), el constructor de prompts de caja y punto de SAM dentro de `meta_client.py` (B y C) y la agregación por profundidad en `geometry.py` (D).
Desde D (28 oct), cada pieza de Muse Code pasa además por una segunda sesión de Muse Code que solo revisa, sin escritura, como recomendó Agents 102; las dos trazas se publican.
Antes de publicar más trazas, resolver o explicar el `"model": "muse-spark-1.3-contributor"` de `docs/muse-code/verify-1.json`.

No se hace: LoRA con el Kaggle NC, una traza de barreno presentada como real, fotos privadas por créditos gratis, quitar el Split manual, Muse Image u otro proveedor.

## Plan del tercer análisis (28 oct, noche)

Adoptado de `docs/ANALISIS-3.md`. A a G hechos y en producción. 1 y 2 hechos y en producción el 28 oct (`b7b8a47`): cookie firmada dueña de cada caja, muestras fijadas de solo lectura, comprobado con dos clientes. Nota estimada: 7.8 hoy, 8.4 a 8.7 con este plan.
3, 5 y 7 hechos y en producción el 28 oct (`6b5907c`): agentes de la caja del recorrido en 101 s en producción (antes unos 3 min; 73 a 96 s en local), con todas las verificaciones; NTS 1981 en 58 s (SAM y Spark 142 a 45 s) y su fila de madera sin piezas en la madera (quedan dos orillas de 7.5 y 2 cm por la calibración); `verify.check_role` por Muse Code (constructor, revisor, constructor) y acciones de una lista cerrada. Ruta de operaciones `POST /api/ops/handoffs/{id}` para volver a correr los agentes de una caja fijada.
Lo que falta ya no es alcance: es producción y pulido.

| Fecha | Puntos | Objetivo | Listo cuando |
|---|---|---|---|
| mié 29 oct | 1 y 2 | Subidas por visitante (cookie firmada dueña de cada caja; lista e imágenes solo para el dueño). Muestras de solo lectura: el recorrido y el barreno fijados por id, y "Try a sample box" crea una copia del visitante. Retirar de la vista pública las cajas de prueba del jurado | Desde dos navegadores, uno no ve las cajas del otro; aprobar una muestra no cambia el recorrido ni el barreno |
| jue 30 oct | 3, 5 y 7 | Agentes más rápidos (juez en paralelo, prompt caching, aviso de tiempo con el paso actual); clase `empty` en la localización de Spark para compartimentos sin núcleo, contada como no recuperada; acciones de los borradores desde una lista cerrada, nunca "stop drilling", revisado por `verify.py` y el juez | Agentes en menos de 2 min en la caja del recorrido; NTS 1981 sin piezas en la fila vacía; ningún borrador dice "stop drilling" |
| vie 31 oct | 6 | Barreno 3D con las tiras reales de la foto sobre el cilindro y selector de barreno (U12G y Onkalo) | La toma final del video muestra la foto real sobre el cilindro |
| sáb 1 nov | 4, 8 | Pulido (tarjeta del recorrido, conteos de piezas, decimales, chips), prueba de abuso otra vez, `prewarm_demo.py` sin llamadas en vivo, desplegar. Plan B de 4: una línea en la página y en el video que explica cuándo corren laboratorio y finanzas. Cierre de H | Una pasada como juez sin hallazgos nuevos |
| dom 2 nov | | Congelar. Ensayo y tomas crudas | |

Orden de recorte: 6, 5, 8. Nunca 1 y 2.
Video: seguir `docs/ANALISIS-3.md` sección 6. Abrir con el rechazo y cerrar con el barreno; partir los agentes con un corte ("about two minutes later"); no decir que Spark mejora a SAM en general.
