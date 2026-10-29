# Cuarto análisis de CoreSight (29 oct): pasada corta antes del video

Versión: `main` y producción en `0fe8309` (imagen `736444a`).
Qué probé, en producción:
- El recorrido completo de 7 pasos y el barreno 3D con los dos barrenos.
- Privacidad con tres clientes: dos `curl` con cookies separadas (A sube, B intenta leer y cambiar) y el navegador como tercer visitante.
- Una charola pública nueva (NTS 1981, dominio público).
- Los textos de los agentes y la tabla de modelos.

Capturas en `docs/analisis-4/`.

## 1. Veredicto

Ocho de los diez hallazgos del tercer análisis están resueltos o en el nivel que se puede alcanzar sin una caja de mina.
Encontré dos problemas nuevos:
- El recorrido gasta el cupo de análisis de las fotos subidas, y ese cupo es compartido.
- Una charola nueva puede pasar la compuerta con la calibración mal recortada.

Nota: **8.4** (antes 7.8). El video puede empezar después de arreglar el punto N1 (30 min).

## 2. Los 10 hallazgos del tercer análisis

| # | Hallazgo | Estado | Evidencia |
|---|---|---|---|
| 1 | Subidas públicas | Resuelto | A subió `4e03654bb0db`. Para B, la caja, `tray.jpg`, `log.csv` y aprobarla dan 404, y su lista sale vacía. Mis cajas del 28 oct ya dan 404 |
| 2 | Muestras alterables | Resuelto | B recibe 403 al cambiar una rotura y al aprobar la muestra fijada `e4618e99ad0b`. El recorrido abre una copia propia (`owner` mío, `pinned` false) y ahí sí se puede corregir. El aviso "Read-only sample. Open my own copy" se entiende |
| 3 | Agentes lentos | Mejor, no resuelto | En la caja del recorrido: agente de barreno 24 s más 30 s del juez, ruteo 23 s, seguridad 24 s más 20 s. Unos 100 s antes de ver el borrador. En el video hay que cortar |
| 4 | Laboratorio y finanzas nunca corren | Plan B en pantalla | La línea "Lab and finance run when sulfides are visible; no openly licensed full tray we found shows them" está debajo del ruteo. La causa sigue ahí: no hay caja de mina |
| 5 | Charola nueva lenta y mal medida | Velocidad resuelta, medida no | Tardó 20 s (con caché). Pero la calibración recortó solo unas 3.5 filas de la charola y las partió en 5 ([06-nts1981-charola-recortada.jpg](analisis-4/06-nts1981-charola-recortada.jpg)). Las filas 2 y 5 caen sobre tablillas, con 21.9 cm y 9.6 cm de "núcleo". RQD 69.6 % y TCR 100 % sin sentido. Con confianza 0.68 la compuerta la deja pasar. El 28 oct lo atribuí a una fila vacía; la causa es la calibración |
| 6 | 3D plano | Resuelto | La foto real envuelve el cilindro a su profundidad, con hueco honesto y selector U12G/Onkalo; el contraste con la roca buena de Onkalo funciona ([04](analisis-4/04-3d-u12g.jpg), [05](analisis-4/05-3d-onkalo.jpg)) |
| 7 | "Do not continue drilling" | Resuelto | El check nuevo "Proposes only, never stops the operation" pasa en los dos borradores. Las acciones salen como chips cerrados: "Warn geotechnics", "Check ground support", "Scale and inspect the walls", "Geotechnical review before the next run" ([03](analisis-4/03-agentes-propone.jpg)) |
| 8 | Pulido | Casi | Ya están: el conteo de piezas ("33 pieces ...; 35 once cut at the run marks"), profundidades a 2 decimales, el crédito y la tarjeta en el último paso. Queda la tarjeta del paso 1, que tapa la caja de razones cuando la ventana mide menos de unos 1100 px ([02](analisis-4/02-tour-rechazo-1000.jpg)). A 1536 px no la tapa ([01](analisis-4/01-tour-rechazo-1536.jpg)). Y el clic en el selector de barreno brinca la página hacia abajo |
| 9 | No prometer que Spark mejora SAM | Solo video | Ver sección 4 |
| 10 | Sin mina ni geólogo | Pendiente | Mismas muestras |

## 3. Nuevo

| # | Hallazgo | Evidencia | Por qué pesa | Arreglo | Costo |
|---|---|---|---|---|---|
| N1 | **El recorrido gasta el cupo de las subidas.** `POST /api/tour/not-a-box` llama a `start(..., visitor)`. Eso descuenta del límite por visitante (5 en 10 min por IP) y del límite compartido de **20 por hora** (`deploy/compose.yml:11`) | `api.py:678` a `685` y `536` a `540` | Si los jueces de Meta comparten IP de oficina, cinco recorridos en 10 minutos bloquean el paso 1 para todos. Con 20 por hora compartidos, un juez que sube su foto después de varios recorridos puede recibir "límite alcanzado". Sería el peor momento para fallar | Pasar el paso 1 por el cupo de las muestras (`visitor=None`) o servir una caja rechazada fija | 30 min |
| N2 | **Una charola nueva pasa la compuerta mal recortada** (punto 5 de arriba) | Confianza de calibración 0.68 y 5 filas impuestas a una charola recortada | Un juez curioso sube otra foto pública y el primer número que ve está mal. Queda "under review", pero el RQD se muestra igual | Si la confianza está entre 0.5 y 0.8, mostrar las filas encontradas sobre la foto y pedir confirmar antes de medir, o subir el umbral. Al menos un aviso visible "calibration uncertain: check the rows" | 2 a 3 h |
| N3 | **La caja de los agentes se aprobó sin correcciones** ("The geologist kept 76 of 76 values... Nothing changed yet") | Tabla de modelos de `6fbe95bd3dd7` | La historia dice "the geologist decides" y la caja que muestra los agentes no tiene ninguna decisión del geólogo | En el video, mostrar la corrección en la copia propia antes de aprobar. Si da tiempo, fijar como caja de agentes una aprobada después de dos o tres toques de SAM | 0 a 1 h |

No encontré regresiones en: la compuerta (captura rechazada en vivo), el toque de SAM, el CSV, el móvil y el barreno 3D.

## 4. Calificación

| Criterio | Peso | 28 oct | Hoy | Por qué |
|---|---|---|---|---|
| Impacto | 30% | 7 | 7.5 | El 3D con foto real y el contraste Onkalo/U12G hacen visible el barreno. Siguen faltando la mina y el geólogo |
| Uso de Meta | 25% | 8.5 | 9 | Agentes en paralelo, juez de Spark en cada hito, `check_role` de Muse Code con revisor |
| Demo | 25% | 7.5 | 8.5 | Privacidad, 3D, acciones cerradas. Le restan N1, N2 y los 100 s de agentes |
| Técnica | 20% | 8.5 | 9 | Dueño por cookie firmada, muestras de solo lectura, 403 y 404 correctos |
| **Total** | | **7.8** | **8.4** | Con N1, N2 y una caja de mina: 8.6 a 8.8 |

## 5. Guion del video: ajustes y tomas

El orden de la sección 6 del tercer análisis sigue valiendo. Cambios:

| Tiempo | Ajuste |
|---|---|
| 0:25 a 0:40 | Paso 1 del recorrido grabado a 1536 px de ancho, para que la tarjeta no tape las razones. Sumar el primer plano de Potter rechazado (2 s) |
| 1:20 a 1:50 | Grabar en una **copia propia** de Nevada caja 1, tramo 2: tres toques de SAM, RQD de 38.6 a 21.1. Luego aprobar esa misma copia, para que los agentes salgan de una caja con decisiones del geólogo (N3) |
| 1:50 a 2:15 | Partir los agentes con un corte ("about 90 seconds later"). Mostrar el check "Proposes only, never stops the operation" y los chips de acciones. Leer la línea del plan B mientras se ven "Not needed" |
| 2:15 a 2:25 | El 3D: U12G con la foto real girando 3 s, luego cambiar a Onkalo. Después de cambiar, hacer scroll a mano de vuelta al 3D |
| 2:25 a 2:45 | Igual. Una traza de Muse Code constructor y otra revisor, 3 s |

No grabar: una charola nueva subida en vivo (N2) ni el recorrido justo después de varias pruebas (N1).

Tomas y resolución:

| Toma | Cómo | Resolución |
|---|---|---|
| Recorrido, pasos 1 a 7 | Chrome a pantalla completa, ventana CSS de 1536 x 864 (1920 x 1080 al 125 %) | 1920 x 1080, 30 fps |
| Toques de SAM y aprobación en la copia propia | Misma ventana; acercar en edición a la tira de la fila, porque se ve delgada | 1920 x 1080, 30 fps; recorte 2x en edición |
| Agentes completos | Misma ventana, grabar los 100 s reales y acelerar en edición | 1920 x 1080, 30 fps |
| 3D girando, U12G y Onkalo | Arrastre lento con el mouse | 1920 x 1080, 60 fps si el equipo aguanta (giro más suave) |
| Glimmer sin red | Según `docs/CLIP_GLIMMER.md`: terminal y Wi-Fi apagado visibles | 1920 x 1080, 30 fps |
| Trazas de Muse Code | `docs/muse-code/*.json` en el editor, letra grande | 1920 x 1080 |
| Clip vertical para X | Portada, rechazo, toque de SAM y 3D en un teléfono o emulado a 390 x 844 | 1080 x 1920, 30 fps |

Antes de grabar: arreglar N1 y correr `scripts/prewarm_demo.py https://coresight.analizac.com`, que debe dar 0 llamadas en vivo.

## 6. Cajas que dejé en producción

No hay endpoint para borrar cajas, así que no borré ninguna. Ningún otro visitante las ve:
- `4e03654bb0db` (JUDGE4-NTS1981), del cliente A.
- Mi copia de Nevada caja 3 `3ca6e35d0b53` y dos cajas `NOT-A-CORE-BOX` del recorrido (`1c79ef96d335`, `d0a56cbaf080`), del navegador.
- Las del 28 oct (`f89f9e7a2fa6`, `2893d3127a8b`) quedaron sin dueño y dan 404.

Si se quieren quitar, hay que borrarlas en el VPS desde la carpeta de revisiones del contenedor.
