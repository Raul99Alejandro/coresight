# Recorrido de 60 s (punto G)

Botón "Take the 60-second tour" en la portada y "Tour" en la barra de cualquier página.
Cada paso abre el producto real (nada es una animación hecha aparte) y su texto es la línea de voz del video del 3 nov.
Flechas izquierda y derecha avanzan; Esc sale. El código vive en `src/coresight/web/index.html` (`Tour`).

| Paso | Qué abre | Línea (inglés, la del video) | Tramo del guion (`ANALISIS-2.md` sección 7) |
|---|---|---|---|
| 1. It knows when not to measure | `POST /api/tour/not-a-box`: nuestra propia captura de pantalla pasa por la compuerta. El primer rechazo corre de verdad; cada recorrido después recibe su copia propia, sin gastar ningún cupo (N1 del cuarto análisis). Con ventanas de 900 a 1100 px el rechazo se corre a la izquierda de la tarjeta | A screenshot goes in. Calibration finds no tray slats, so there is no scale, and Muse Spark says what the photo shows. CoreSight refuses it with the reasons: SAM never runs and no RQD is made up. | 0:25 a 0:40 |
| 2. A real core box | Nevada U12G caja 3 (dominio público) analizada en vivo con la caché | Nevada Test Site, drill hole U12G, box 3: public domain. OpenCV straightens the tray and sets the scale, then the models work row by row, live. | 0:40 a 1:00 |
| 3. Spark points, SAM cuts | Vista "SAM masks" de la misma caja | Muse Spark marks the core and what is not core: cards, wax, wooden blocks. SAM 3.1 cuts each piece inside those boxes. These are its masks. | 1:00 a 1:20 |
| 4. Code measures, the geologist corrects | Panel del tramo con la rotura dudosa | geometry.py turns the pieces into RQD per run: no model touches the number. Tap the photo where a break is wrong and SAM cuts that piece again; the RQD is recalculated. | 1:20 a 1:50 (grabar aquí el toque de SAM) |
| 5. Approve | Botón Approve resaltado, sin pulsarlo | Approving locks the box and starts the agents. Here we leave it under review: the next step shows a box approved before. | 1:50 |
| 6. Agents, verified in two layers | La caja fijada en `CORESIGHT_TOUR_AGENTS_BOX` (`deploy/compose.yml`): Nevada caja 1, `00aaf0cd3771`, aprobada después de 6 correcciones del geólogo. La tabla de modelos dice "The geologist changed 6 of 80 values" | A hole agent reads the trends between boxes, Muse Wonder decides who needs to know, and area agents draft. Code checks first, then Muse Spark as a judge, three attempts at most, then a person. Nothing is sent. | 1:55 a 2:10 |
| 7. From boxes to a drill hole | Vista de barreno con 3D: la foto de cada caja envuelve el cilindro a su profundidad (`hole.core_pieces`); selector U12G y Onkalo; "RQD colour" prende la capa de Deere | Approved boxes join by depth into one hole, with weak zones flagged by code. In 3D each box photo wraps the core at its measured depth, empty where no core came back. The trace is an example. Switch to Onkalo for good rock. | 2:10 a 2:20 (cierre: cambiar a ONK-DTPH5.1 en el selector bajo el 3D; la tarjeta queda a la izquierda) |

En el paso 6, cuando laboratorio y finanzas salen "Not needed", la página dice debajo de las áreas, y el video lo repite en voz: "Lab and finance run when sulfides are visible; no openly licensed full tray we found shows them." La línea enlaza a sus tests (`test_verify_milestones.py`: laboratorio debe correr con sulfuros, finanzas sigue a laboratorio; `test_agents.py`: laboratorio, seguridad y planta en paralelo y finanzas cotiza lo de laboratorio). Es el plan B del punto 4 de `docs/ANALISIS-3.md` mientras no haya una caja de mina con permiso.

La caja de agentes (`00aaf0cd3771`) tiene decisiones reales, todas visibles en la foto y todas acercan la caja a nuestra etiqueta:
- Tramo 1: la "pieza" de 0 a 8.3 cm de la fila 1 es la tarjeta amarilla "Run #1". Se quitó: TCR de 53.8 a 48.4 (etiqueta 48.5).
- Tramo 3: la "pieza" de 12.9 a 20.9 cm de la fila 4 es la tarjeta "Run #3". Se quitó: RQD de 33.5 a 79.5 (etiqueta 80.8), TCR de 100 a 98.1 (97.4).
- Tramo 2: una astilla de 0.4 cm junto a la tarjeta, quitada, y dos roturas dudosas al final de fila, naturales como en la etiqueta. Tramo 1: una rotura dudosa más, natural.
- Los agentes: hallazgo del barreno (zona débil de 0.00 a 3.41 m) y borrador de seguridad verificado con las cuatro acciones cerradas.

Ojo con el guion: el toque de SAM de "38.6 a 21.1" en Nevada caja 1, tramo 2 ya no se reproduce. Desde el punto B, Spark y SAM cortan ese tramo bien a la primera (RQD 15.1 contra 15.9 de la etiqueta) y un toque ahí deja la pieza igual. Para la toma del geólogo usar una copia propia de Nevada caja 1 y quitar las dos tarjetas (botón de quitar pieza en el panel del tramo): el RQD del tramo 3 sube de 33.5 a 79.5, contra 80.8 de la etiqueta. Es la corrección que se ve y se puede contar.

Calibración dudosa (N2): si la confianza de calibración queda entre 0.5 y 0.9, la caja abre con las filas encontradas sobre la foto y el aviso "Calibration uncertain: check the rows". No muestra RQD, CSV ni Approve hasta que alguien pulse "The rows are right". "The rows are wrong" rechaza la caja con la razón. Las muestras dan 1.00; NTS 1981 da 0.68.

Antes de grabar: `scripts/prewarm_demo.py https://coresight.analizac.com` debe decir 0 llamadas en vivo y `showcase` completo.
El paso 4 solo resalta el panel; la corrección real se graba a mano en ese momento.
