# Recorrido de 60 s (punto G)

Botón "Take the 60-second tour" en la portada y "Tour" en la barra de cualquier página.
Cada paso abre el producto real (nada es una animación hecha aparte) y su texto es la línea de voz del video del 3 nov.
Flechas izquierda y derecha avanzan; Esc sale. El código vive en `src/coresight/web/index.html` (`Tour`).

| Paso | Qué abre | Línea (inglés, la del video) | Tramo del guion (`ANALISIS-2.md` sección 7) |
|---|---|---|---|
| 1. It knows when not to measure | `POST /api/tour/not-a-box`: nuestra propia captura de pantalla pasa por la compuerta y se rechaza en vivo | A screenshot goes in. Calibration finds no tray slats, so there is no scale, and Muse Spark says what the photo shows. CoreSight refuses it with the reasons: SAM never runs and no RQD is made up. | 0:25 a 0:40 |
| 2. A real core box | Nevada U12G caja 3 (dominio público) analizada en vivo con la caché | Nevada Test Site, drill hole U12G, box 3: public domain. OpenCV straightens the tray and sets the scale, then the models work row by row, live. | 0:40 a 1:00 |
| 3. Spark points, SAM cuts | Vista "SAM masks" de la misma caja | Muse Spark marks the core and what is not core: cards, wax, wooden blocks. SAM 3.1 cuts each piece inside those boxes. These are its masks. | 1:00 a 1:20 |
| 4. Code measures, the geologist corrects | Panel del tramo con la rotura dudosa | geometry.py turns the pieces into RQD per run: no model touches the number. Tap the photo where a break is wrong and SAM cuts that piece again; the RQD is recalculated. | 1:20 a 1:50 (grabar aquí el toque de SAM) |
| 5. Approve | Botón Approve resaltado, sin pulsarlo | Approving locks the box and starts the agents. Here we leave it under review: the next step shows a box approved before. | 1:50 |
| 6. Agents, verified in two layers | La caja aprobada más reciente con agentes terminados (`/api/showcase`) | A hole agent reads the trends between boxes, Muse Wonder decides who needs to know, and area agents draft. Code checks first, then Muse Spark as a judge, three attempts at most, then a person. Nothing is sent. | 1:55 a 2:10 |
| 7. From boxes to a drill hole | Vista de barreno con 3D | Approved boxes join by depth into one hole, with weak zones flagged by code. The 3D trace is an example; every number in it is measured. | 2:10 a 2:20 |

Antes de grabar: `scripts/prewarm_demo.py https://coresight.analizac.com` debe decir 0 llamadas en vivo y `showcase` completo.
El paso 4 solo resalta el panel; el toque real de SAM se graba a mano en ese momento (tarda unos segundos por la API).
