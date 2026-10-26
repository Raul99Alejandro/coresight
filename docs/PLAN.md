# Plan de 10 días

Entrega oficial: **mié 4 nov 2026, 21:00 ET = 20:00 hora de Zacatecas**. Meta interna: enviar antes de las **18:00**.
Kickoff: lun 26 oct, livestream a las 12:00 PM (la página dice EST): 11:00 en Zacatecas, confirmarlo en la transmisión.
Juzgado: 4 al 8 nov. Final en vivo y ganadores: 9 nov.

| Día | Fecha | Objetivo | Listo cuando |
|---|---|---|---|
| 0 | dom 25 oct | Repo, plan, buscar fotos de cajas de núcleo | Repo con tests en verde y CI; lista de al menos 3 fuentes públicas de fotos con licencia anotada |
| 1 | lun 26 oct | Kickoff, API key, smoke test de SAM 3.1 y Muse Spark con 1 foto | Reglas oficiales leídas y aceptadas; `meta_client` sin TODO; SAM devuelve máscaras y Muse Spark devuelve JSON que pasa `GeologyDescription` con 1 foto |
| 2 | mar 27 oct | Dataset de 20 a 50 cajas y RQD manual de al menos 10 | 20+ fotos en `data/raw/` con fuente; 10+ etiquetas JSON que validan con `BoxLabel` |
| 3 | mié 28 oct | Calibración | Error px→cm < 2% en las cajas etiquetadas; filas recortadas correctamente |
| 4 | jue 29 oct | Segmentación SAM 3.1 de piezas y fracturas en cm | Lista de `Piece` por fila en cm para las 10 cajas etiquetadas; caché por hash de imagen |
| 5 | vie 30 oct | Motor geométrico conectado | Una foto produce RQD, TCR y FF por intervalo de punta a punta |
| 6 | sáb 31 oct | Muse Spark con descripciones y anomalías | JSON validado por intervalo; las 3 anomalías se disparan en casos de prueba |
| 7 | dom 1 nov | UI de revisión y export CSV | El geólogo corrige un intervalo, la corrección se guarda y el CSV se descarga |
| 8 | lun 2 nov | Handoffs a laboratorio y seguridad con aprobación | Borradores generados solo después de aprobar; demo desplegada con URL pública |
| 9 | mar 3 nov | Evaluación RQD automático vs manual | MAE de RQD (y TCR) en el README con tabla y casos de falla |
| 10 | mié 4 nov | Video demo de 3 min o menos, README, enviar | Enviado antes de las 18:00 con repo, video y demo |

## Riesgos y plan B

| Riesgo | Plan B |
|---|---|
| Sin datos reales | Imágenes públicas y etiquetar 10 cajas a mano |
| SAM no separa fracturas finas | Detectar cortes por perfil de intensidad a lo largo del eje del núcleo |
| Límites de la API | Caché por hash de imagen (`data/cache/`) y reintentos con backoff |
| Falta de tiempo | Recortar handoffs, nunca la evaluación |
| Reglas oficiales piden algo no previsto (duración de video, repo público, formato) | Leerlas el día 1 y ajustar este plan ese mismo día |
| Muse Spark o SAM 3.1 con restricción regional o de cuota desde México | Probar el día 1; si falla, preguntar en Discord y usar créditos de partners (Baseten, Modal, Fireworks) con modelos open-weights |

## Ajustes por la investigación (25 oct)
Lo que dicen la página oficial y la aplicación, y cómo cambia el plan:

- **CI en pausa.** Actions no corre por la facturación de la cuenta, que se arregla hasta el próximo mes. El workflow queda solo manual. Mientras tanto, antes de cada push: `.venv\Scripts\python -m pytest -q` y `.venv\Scripts\python -m ruff check .`. Si el repo se hace público, Actions es gratis y se reactiva el push.
- **Track Startup se juzga por "technical execution" y "whether it holds up in production".** Por eso se agregó: CI con tests y ruff desde el día 0, caché y reintentos en `meta_client` (día 4), demo desplegada con URL pública (día 8), manejo de errores visible en la UI (fotos malas, caja sin escala).
- **Final en vivo el 9 nov.** Tener la demo desplegada estable después de la entrega y un guion de 3 minutos ensayado.
- **Reglas oficiales aún no publicadas** al 25 oct. Revisarlas el día 1: duración del video, si el repo debe ser público, si se permite código previo y la plataforma de entrega.
- **Muse Code está prometido en la aplicación.** Usarlo en al menos una pieza real y documentarlo en `docs/APPLICATION.md`.
- **Modo Contributor de Muse Spark** es más barato pero Meta puede entrenar con esos datos. Solo usarlo con imágenes públicas, nunca con datos de clientes.
- **Workshops y office hours en Discord** del 27 oct al 4 nov. Llevar preguntas concretas de SAM 3.1 (prompts para fracturas) a las office hours.
