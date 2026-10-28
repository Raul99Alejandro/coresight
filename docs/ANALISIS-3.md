# Tercer análisis adversarial de CoreSight (28 oct)

Punto de vista: un juez de Meta que abre https://coresight.analizac.com, toma el recorrido, sube sus propias fotos y mira el repo 5 minutos.
Versión probada: `main` en `300f2f7`, igual a producción. Puntos A a G del segundo análisis hechos y desplegados.

Qué hice:
- Portada, recorrido de 60 s completo (7 pasos), vista de máscaras, panel de tramo, agentes con dos capas, barreno 3D, CSV, móvil.
- Abuso en producción: la captura del recorrido, un primer plano de núcleo sin charola (Potter 07) y una charola pública que CoreSight nunca había visto (Nevada Test Site 1981, dominio público, con carta de color).
- Toque de SAM en vivo sobre esa charola nueva.
- No aprobé ninguna caja en producción a propósito: ver hallazgo 2 en la sección 3.
- No probé una selfie: no hay una foto pública de una persona en el repo y no bajé ninguna. Hay tests que la cubren (`tests/test_gate.py`, `tests/test_abuse.py`).

Capturas en `docs/analisis-3/`.

---

## 1. Veredicto corto

El salto es real. Ya no se ve como "un analizador de fotos".
La portada promete un barreno, el recorrido abre con un rechazo, Spark le pasa cajas a SAM, el geólogo toca la foto y SAM corta otra vez en 1.6 s, y los agentes llegan verificados en dos capas con el vocabulario de Agents 102. Muse Code aparece como constructor y revisor en seis piezas.

Lo que hoy haría perder puntos ya no es de alcance. Es de **producción y de pulido**:
1. Todo lo que sube un visitante lo ven los demás, y cualquiera puede cambiar las cajas que alimentan el recorrido.
2. Los agentes tardan unos 3 minutos de punta a punta.
3. En las muestras públicas, laboratorio, planta y finanzas nunca se disparan.
4. El barreno 3D es un palo de 8 m con dos tramos rojos.

Calificación ponderada hoy: **7.8** (antes 6.8). Con los arreglos de la sección 4: **8.4 a 8.7**.

---

## 2. Recorrido como juez

| Paso | Lo que vi | Lectura del juez |
|---|---|---|
| Portada | "From a photo of a core box to a logged drill hole.", caja real de Nevada, los cuatro actores, bloque "Then the drill hole" con 2 cajas, 8.0 m y 2 zonas débiles, y "It knows when not to measure" ([01-portada.jpg](analisis-3/01-portada.jpg)) | Se entiende en 10 s y ya no es un analizador de fotos. Bien |
| Tour 1: rechazo | La captura se rechaza con dos razones: Spark ("screenshot of CoreSight software UI page") y calibración (confianza 0.00, sin escala) ([02-tour-rechazo.jpg](analisis-3/02-tour-rechazo.jpg)) | Muy buen arranque. La tarjeta del recorrido tapa parte de la caja de razones en una ventana de 800 px |
| Tour 2: caja real | Nevada caja 3 enderezada, roturas por color ([03-tour-caja.jpg](analisis-3/03-tour-caja.jpg)) | Bien |
| Tour 3: Spark marca, SAM corta | Máscaras de colores por pieza; las tarjetas y el bloque quedan fuera, las muestras enceradas dentro ([04-mascaras-spark-sam.jpg](analisis-3/04-mascaras-spark-sam.jpg)) | Es la imagen más fuerte para el video |
| Tour 4: código mide | Panel del tramo: RQD 23.6 %, TCR 100 %, FF 12.47, cada uno con `geometry.py` | Claro |
| Tour 6: agentes | Agente de barreno con tendencias de `hole.py`, `verify.py` 3 de 3, Spark como juez 13 de 13, "2 attempts of 3", ruteo verificado 4 de 4, alerta de seguridad con 4 checks y 21 de 21 afirmaciones respaldadas ([05-agentes-dos-capas.jpg](analisis-3/05-agentes-dos-capas.jpg)) | Lo más "agentic" del proyecto y se ve serio. Pero es una pared de texto y los tiempos suman unos 3 minutos |
| Tour 7: barreno | Columna de 0 a 8 m con hueco honesto de 3.41 a 5.79 m, dos zonas débiles, 3D "Example trace (azimuth 045, dip -70)" ([06-barreno-3d.jpg](analisis-3/06-barreno-3d.jpg)) | Honesto. Pero el 3D es una línea con dos segmentos rojos: no sorprende |
| Al salir del recorrido | La tarjeta "7 of 7" se quedó encima al abrir otra caja; Esc no la cerró ([11-tour-pegado.jpg](analisis-3/11-tour-pegado.jpg)) | Detalle visible |
| Subir un primer plano (Potter 07) | Rechazado en 0.06 s: "close-up of mineralized drill core pieces", sin tablillas | Correcto |
| Subir una charola nueva (NTS 1981) | Aceptada. Calibración 0.68, 5 filas, **SAM 142 s** porque Spark encajonó las 5 filas, RQD 72 % "Fair". La charola tiene una fila de abajo vacía de madera y sale con piezas y TCR 100 % ([07-caja-nueva-juez.jpg](analisis-3/07-caja-nueva-juez.jpg)) | El juez espera 2.5 min y recibe una medición dudosa. Queda "under review", lo cual es correcto, pero el primer número que ve parece inflado |
| Toque de SAM | Diálogo con la fila; un toque y "SAM 3.1 cut 22.2 cm in 1.6 s. Numbers recalculated." con la máscara morada ([08-toque-sam.jpg](analisis-3/08-toque-sam.jpg)) | El mejor momento interactivo. La tira de la fila es delgada en laptop |
| CSV | `log.csv` correcto, con `complete=False` en el tramo que viene de otra caja | Bien |
| Móvil | Portada y barreno sin scroll horizontal (375 px), encabezado arreglado ([09](analisis-3/09-movil-portada.jpg), [10](analisis-3/10-movil-barreno.jpg)) | Bien |

---

## 3. Lo que todavía hace perder puntos

Ordenado por impacto entre costo. Días de código: 29 oct a 1 nov.

| # | Hallazgo | Evidencia | Por qué pesa | Arreglo | Costo | Día |
|---|---|---|---|---|---|---|
| 1 | **Las subidas de un visitante son públicas.** `GET /api/boxes` lista todas las cajas, el menú "Boxes" las muestra y `/api/boxes/{id}/tray.jpg` sirve la foto de otro (probé la mía: 200). El docstring de `showcase` dice "Uploads are never shown to other visitors", pero el menú sí | `api.py:593`, `web/index.html:1087`; mis cajas `JUDGE-commons_nts_1981` y `JUDGE-commons_potter_07` aparecen en la lista pública | Startups se juzga por "holds up in production". Un juez de Meta que sube una foto y la ve en otra ventana lo anota. Con una caja real de mina sería una fuga | Un identificador por navegador (cookie firmada) dueño de cada subida; la lista y las imágenes solo para el dueño; muestras sin dueño | 0.5 día | 29 oct |
| 2 | **Cualquier visitante puede cambiar las cajas del recorrido.** Las muestras son compartidas y sin dueño: un juez que corrige mal y aprueba Nevada cambia lo que el siguiente ve en el recorrido y en el barreno (`showcase` toma la aprobada más reciente; `hole_view` toma todas las aprobadas) | `api.py:502` a `518` | Durante el juzgado (5 al 8 nov) un solo juez puede dejar la demo rara para los demás | Fijar las cajas del recorrido y del barreno por id, de solo lectura; "Try a sample box" crea una copia del visitante | 0.5 día, junto con 1 | 29 oct |
| 3 | **Agentes lentos.** En la caja del recorrido: agente de barreno 48 s + 29 s del juez, ruteo 37 s, seguridad 29 s + 21 s. Unos 3 minutos antes de ver el borrador | Tiempos que la propia página muestra en [05](analisis-3/05-agentes-dos-capas.jpg) | En el video se puede cortar; en vivo el juez se va. Agents 102 dice mostrar el costo, no esconderlo, pero 3 minutos es mucho | Correr al juez sobre todos los borradores en paralelo, caché de prompts fijos (prompt caching de la doc de Meta), y que la página diga "about 2 minutes" con el paso actual en una línea | 0.5 día | 30 oct |
| 4 | **Tres de cuatro áreas dicen "Not needed" en todas las muestras públicas.** No hay ninguna charola pública completa con sulfuros, así que laboratorio y finanzas nunca corren frente al juez | Caja 3: lab, plant y finance "Not needed" | El premio Agentic se juzga por "effectiveness and practical utility". Un juez ve un agente útil, no cuatro | Lo único que lo arregla de verdad es la caja de una mina con permiso (punto H, pendiente). Plan B honesto: una línea en la página y en el video, "lab and finance run when sulfides are visible; no openly licensed full tray shows them", y mostrar sus tests | Llamadas de Raúl; plan B 1 h | Cierre 1 nov |
| 5 | **Una charola nueva tarda 2.5 min y mide una fila vacía.** En NTS 1981, Spark encajonó las 5 filas (SAM 142 s) y la fila de madera vacía salió con piezas; TCR 100 % | [07-caja-nueva-juez.jpg](analisis-3/07-caja-nueva-juez.jpg) | Es lo que hará un juez curioso: subir otra foto pública. El primer número que ve es dudoso | Clase `empty` en la localización de Spark (compartimento sin núcleo) y que cuente como no recuperado; avisar "Muse Spark is boxing 5 rows, about 2 minutes" | 0.5 día | 30 oct |
| 6 | **El barreno 3D no sorprende.** Dos segmentos en un palo de 8 m; Onkalo (17.9 a 27.2 m, roca buena) existe como barreno pero el recorrido no lo usa | `/api/holes` devuelve ONK-DTPH5.1 y U12G-GF-GT2 | Es la toma que cierra el video. Hoy se ve como un diagrama | Envolver el cilindro con las tiras reales de la foto de cada fila (núcleo "desenrollado" en 3D, todo medido), y un selector de barreno para mostrar el contraste con Onkalo | 1 día | 31 oct |
| 7 | **Recomendación que excede el rol.** El borrador de seguridad dice "Do not continue drilling until the safety team reviews." y el juez de Spark lo aprueba (21 de 21) | Texto de la alerta en la caja del recorrido | Un geotecnista juez sabe que parar la perforación es una decisión cara que no toma un borrador. Debilita el "human decides" | Regla en `verify.py`: las acciones salen de una lista cerrada (revisar soporte, revisar antes del siguiente tramo, avisar) y nunca "stop drilling"; el juez la revisa | 2 h | 30 oct |
| 8 | **Detalles de pulido** | Tarjeta del recorrido que tapa la caja de razones a 800 px y que sigue abierta al salir; "33 pieces" contra "35 of 35 pieces kept" en la tabla de modelos; profundidades con 3 decimales en textos de agentes (5.791) y con 2 en la página (5.79); chips pegados al texto en la tabla del barreno ("fragmentedlow recoveryother" en el texto accesible) | Capturas 02 y 11, texto de la página | Cada uno es menor; juntos restan en "se disfruta" | Una pasada | 2 a 3 h | 1 nov |
| 9 | **Spark más SAM no mejora en Kaggle.** `spark+sam` contra `sam`: +2.4 [-1.0, +7.9] en RQD; con las capas, +0.7. Producción usa `fallback+` (Spark solo donde "stone" no encuentra nada), que no cambia Kaggle y ayuda en las públicas | `outputs/eval/report.md`, sección "Spark localizes, SAM cuts" | Bien reportado. El riesgo es que el video diga "Spark makes SAM better" | En el video: "where SAM's text prompt finds nothing, Spark's boxes recover the row". No prometer mejora general | 0 | Video |
| 10 | **Sin geólogo ni mina.** Las dos fuentes siguen siendo sitios nucleares. La historia de Zacatecas no tiene una caja ni una voz | Muestras de `/api/samples` | Impacto pesa 30 % | Punto H. Es lo que más sube Impacto | Llamadas | Cierre 1 nov |

Lo que ya no hay que tocar: la compuerta de entrada, el toque de SAM, la verificación en dos capas, la evaluación, la procedencia y el registro de Muse Code. Están a nivel de final.

Orden de recorte si falta tiempo: 6, 5, 8. Nunca 1 y 2: son los que un juez del track Startups puede encontrar solo.

---

## 4. Calificación

| Criterio | Peso | 27 oct | Hoy | Por qué cambia | Esperada con los arreglos |
|---|---|---|---|---|---|
| Impacto | 30% | 6.5 | 7 | La unidad ahora es el barreno, con zonas débiles y huecos honestos. Sigue sin mina, sin geólogo y con 3 áreas que nunca corren | 7.5 (8 con H) |
| Uso de Meta | 25% | 7 | 8.5 | Spark localiza y SAM corta con cajas; SAM con puntos en vivo; Spark como juez; Wonder rutea sin reglas fijas; Muse Code constructor y revisor en seis piezas con trazas. Le resta que Spark más SAM no mejora Kaggle y que Wonder es lento | 9 |
| Demo | 25% | 6 | 7.5 | Recorrido de 60 s, rechazo, toque de 1.6 s, portada con caja. Le restan los 3 minutos de agentes, el 3D plano, la caja nueva lenta y los detalles del recorrido. El video sigue sin hacerse | 8.5 |
| Técnica | 20% | 8 | 8.5 | 440 tests, ablación con pares y bootstrap, F reportado sin presumir. Le resta que las subidas son públicas y las muestras se pueden alterar | 9 |
| **Total** | | **6.8** | **7.8** | | **8.4 a 8.7** |

El riesgo "simple image analyzer" bajó de medio a bajo. Lo que lo mantiene vivo: un video que abra con una sola caja. Hay que abrir con el rechazo y cerrar con el barreno.

---

## 5. Plan para los días de código

| Fecha | Qué | Listo cuando |
|---|---|---|
| mié 29 oct | 1 y 2: subidas por visitante, muestras de solo lectura, recorrido y barreno fijados | Desde dos navegadores, uno no ve las cajas del otro; aprobar una muestra no cambia el recorrido |
| jue 30 oct | 3, 5 y 7: juez en paralelo, aviso de tiempo, clase `empty`, lista cerrada de acciones | Agentes en menos de 2 min en la caja del recorrido; NTS 1981 sin piezas en la fila vacía; ningún borrador dice "stop drilling" |
| vie 31 oct | 6: núcleo desenrollado en el 3D y selector de barreno | La toma final del video muestra la foto real sobre el cilindro |
| sáb 1 nov | 8, prueba de abuso completa otra vez, `prewarm_demo.py` con 0 llamadas en vivo, desplegar. Cierre de H | Una pasada como juez sin hallazgos nuevos |
| dom 2 nov | Congelar. Ensayo y tomas crudas | |

---

## 6. El guion de video de la sección 7 del segundo análisis

Sigue valiendo en su orden. El recorrido de 60 s (`docs/TOUR.md`) ya lo sigue paso por paso, así que el video puede grabarse casi entero desde el recorrido. Ajustes con lo que existe hoy:

| Tiempo | Antes | Ahora |
|---|---|---|
| 0:00 a 0:10 | Línea de trabajo previo | Igual |
| 0:10 a 0:25 | El problema con un número | Igual. Si no hay geólogo, usar las cifras de Camimex y Marjoribanks en pantalla |
| 0:25 a 0:40 | Rechazo de una captura | Igual, es el paso 1 del recorrido. Agregar el primer plano rechazado en 2 s para que no parezca un caso único |
| 0:40 a 1:20 | Spark marca, SAM corta, `geometry.py` mide | Igual, con las máscaras (paso 3). Decir "where SAM's text prompt finds nothing, Spark's boxes recover the row", no "Spark makes SAM better" |
| 1:20 a 1:50 | Toque de SAM y recálculo | Igual. Grabar en Nevada caja 1 tramo 2, donde tres toques llevan el RQD de 38.6 a 21.1 contra 15.9 de la etiqueta: es una corrección que se ve y se puede contar |
| 1:50 a 2:20 | Varias cajas, barreno 3D, agente de barreno, borrador verificado | Partir: 1:50 a 2:15 agentes con el vocabulario de Agents 102 ("verification inside the submit step, code first then Muse Spark as a judge, three attempts, then a person"), con un corte que diga "about two minutes later"; 2:15 a 2:25 barreno |
| 2:20 a 2:45 | Evaluación, ablación, Glimmer sin red | 2:25 a 2:45: MAE 11.2 [6.1, 18.9], Glimmer sin red, y 3 s de una traza de Muse Code constructor y revisor |
| 2:45 a 3:00 | Cierre | Igual |

Lo que no debe salir en el video: el 3D girando más de 3 s si no tiene la textura real; la caja nueva de 2.5 min; las tarjetas "Not needed" sin la línea que explica por qué.

---

## 7. Resumen en 10 líneas

1. El salto es real: la nota sube de 6.8 a 7.8 y ya no se lee como "simple image analyzer".
2. Lo mejor: rechazo con razones, Spark que encajona y SAM que corta, toque de SAM en 1.6 s, agentes verificados en dos capas, Muse Code constructor y revisor.
3. Hallazgo 1: las subidas de cualquier visitante salen en el menú público y su foto se puede bajar.
4. Hallazgo 2: cualquiera puede corregir y aprobar las muestras y cambiar lo que el recorrido y el barreno muestran a los demás jueces.
5. Hallazgo 3: los agentes tardan unos 3 minutos de punta a punta.
6. Hallazgo 4: laboratorio, planta y finanzas nunca corren en las muestras públicas; solo una caja de mina lo arregla.
7. Hallazgo 5: una charola nueva tarda 2.5 min y mide como núcleo una fila vacía.
8. Hallazgo 6: el 3D es un palo de 8 m; envolverlo con la foto real lo volvería la toma final.
9. Plan: 29 oct privacidad y muestras fijas, 30 oct velocidad y límites de los agentes, 31 oct 3D con textura, 1 nov pulido y despliegue.
10. El guion sigue valiendo y el recorrido ya es casi el video; partir el bloque de agentes con un corte y no prometer que Spark mejora SAM en general.
