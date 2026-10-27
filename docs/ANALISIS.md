# Análisis adversarial de CoreSight (27 oct)

Propósito: decidir qué cambiar para tener las máximas posibilidades de ganar el track Startups.
Punto de vista: un juez de Meta escéptico y un competidor fuerte.

Fuentes revisadas:
- El repo completo: docs, código en `src/coresight/`, `outputs/eval/report.md`, `outputs/describe/compare.md`, historial de git.
- La guía oficial en Cerebral Valley (reglas, anti-proyectos, rúbrica, premios).
- Discord: #announcements, #faqs, #push-the-frontier, #general, foros #office-hours y #questions (hilos con respuesta de Meta o de CV), canales meta, baseten, modal y fireworks.
- La demo publicada en https://coresight.analizac.com (escritorio y móvil).
- Grabaciones de talleres: Agents 101 todavía no está publicada (ni en #announcements ni en el evento de Vimeo). Revisar Agents 101 y 102 antes del día 8.

---

## 1. Resumen en una pantalla

Nota ponderada estimada hoy: **6.5 de 10**.
Con los cambios de la sección 7: **8.3 a 8.8**, que es zona de top 5 y de pelear el primer lugar.

Lo bueno, que un juez sí va a ver:
- Ingeniería seria: arquitectura neurosimbólica, 138 tests, CI, Pydantic en cada salida, caché, límites de uso, demo desplegada.
- Uso amplio de Meta: SAM 3.1, Muse Spark, Voice Transcribe, Glimmer local y Muse Spark Open en Baseten.
- Un dominio físico real y sin competencia visible en Discord (nadie más hace minería o geología).

Lo que hoy hace perder puntos:
1. **La demo no tiene drama.** Las dos muestras públicas son roca "Excellent" de Onkalo (un repositorio nuclear en Finlandia, no una mina). No hay roca mala, no hay sulfuros, no hay alertas. Los agentes del día 8 no tendrían nada que disparar.
2. **El motor de RQD es trabajo previo.** `geometry.py` no ha cambiado desde el commit `013503a` (25 oct, antes del kickoff). Es la pieza que el pitch llama "el corazón". Si el video lo presume, choca con la regla "la demo solo muestra lo hecho en el hackathon".
3. **Muse Code está prometido y no se ha usado.** El registro en `APPLICATION.md` está vacío y los 19 commits del repo público llevan `Co-Authored-By: Claude`. Un juez de Meta lo va a notar.
4. **La evidencia no está en el repo.** `outputs/` está en `.gitignore`: el reporte de evaluación, la comparación de backends y los logs de Glimmer no son públicos. El README todavía dice "Early scaffold" y "Evaluation: to be filled".
5. **La evaluación es chica y tiene un punto débil.** 39 tramos, 5 de ellos etiquetados por nosotros sobre la misma foto. El mejor MAE (8.6) usa las marcas rojas que el geólogo ya pintó sobre el núcleo.

La buena noticia: vamos muy adelantados.
El plan ponía el día 8 el 1 nov y hoy, 27 oct, ya están los días 0 a 7.
Hay unos **4 días de colchón** para arreglar lo de arriba sin tocar el núcleo.

---

## 2. Calificación por criterio de la rúbrica

### Impacto (30%): 6 de 10

Evidencia a favor:
- Problema real y caro: el logueo manual de núcleo es lento, subjetivo y frena el modelo de recursos.
- Encaja en "Push the Frontier": modelos de Meta conectados a un sistema físico (núcleo de barrenación).
- Zacatecas como origen le da autenticidad (primer productor de plata de México).

Evidencia en contra (lo que diría un juez escéptico):
- No hay ni un número de valor en el README ni en la demo: cuántos metros se barrenan, cuánto cuesta loguear un metro, cuántas horas ahorra.
- No hay un usuario real: ni un geólogo citado, ni una carta de interés, ni una foto de una mina mexicana.
- Las muestras son de Finlandia y de un repositorio nuclear. La historia dice "mina de plata en Zacatecas" y la demo no la respalda.
- "Pre-revenue de AnaliZac" sin cliente piloto es débil para Startups, que se juzga por "aguantar en producción".

Qué lo sube:
- Un geólogo real (de Zacatecas, de preferencia) en 10 a 15 segundos del video: "esto me ahorra X horas por barreno".
- Tres números en el video y en el README, con fuente: metros barrenados al año, tiempo de logueo por caja, costo de un mal RQD (soporte de terreno, dilución). No inventarlos: buscarlos y citarlos.
- Una caja de una mina mexicana, fotografiada con celular y con permiso. Vale más que cualquier mejora de código.

### Uso de las herramientas de Meta (25%): 7 de 10

Evidencia a favor:
- Cinco modelos de Meta con roles distintos y el mismo contrato Pydantic en tres backends (Spark API, Spark Open en Baseten, Glimmer local).
- La UI muestra quién hizo qué ("Models in this box"): tiempo, llamadas, caché y costo. Esto es poco común y les gusta a los jueces técnicos.
- Voice Transcribe con sesgo de idioma y palabras clave en español e inglés.

Evidencia en contra:
- Cada uso, por separado, es "básico": SAM con el prompt "stone", Spark que describe un recorte, Voice que transcribe. La rúbrica pide "sorprendernos".
- Muse Wonder todavía no existe en el código. Hay reportes en Discord de fallas de Wonder (chat que falla 9 de 10 veces, rechazo de la herramienta computer).
- Muse Code prometido y sin uso. En #office-hours Connor (Meta) confirmó que usar Muse Code dentro del producto cuenta para este criterio.
- Las correcciones del geólogo se guardan "para futuro fine-tuning", pero el ciclo no se cierra.

Qué lo sube (en orden de sorpresa por esfuerzo):
- **SAM 3.1 con prompts de punto en la revisión**: el geólogo da clic sobre una pieza mal segmentada y SAM la vuelve a cortar ahí. Es el uso interactivo para el que SAM existe y casi nadie lo muestra.
- **Cerrar el ciclo con modelos abiertos**: usar las correcciones guardadas para un few-shot o un LoRA pequeño de Glimmer (el taller de Fireworks del 30 oct trata justo de entrenar modelos Muse abiertos). Aunque sea una prueba chica, la frase "el modelo abierto aprende del geólogo y corre en la mina sin internet" es muy fuerte.
- **Muse Wonder como orquestador con herramientas reales** (las funciones de `geometry.py` y la tabla de precios como tools), con plan B en Spark 1.3 si Wonder falla.
- **Muse Code de verdad**: construir con él una pieza del día 8 y dejar evidencia (capturas, commits, sección en el README).

### Profundidad técnica (20%): 7.5 de 10

Evidencia a favor:
- Separación limpia: el modelo percibe, el código calcula, el geólogo decide. El LLM nunca calcula el RQD.
- Ablaciones ya medidas (sam, +fill, +profile, +marks).
- Producción: rate limit, límites de tamaño, caché por hash, reintentos, contenedor en 127.0.0.1, llaves fuera de git.

Evidencia en contra:
- n=39 tramos y n=5 en Onkalo. En Onkalo las etiquetas son nuestras, medidas sobre la misma foto. TCR con MAE 0.0 en Onkalo con `fill` se ve sospechoso para un evaluador.
- La variante `+marks` lee las marcas rojas del geólogo. Un juez puede decir que el sistema copia la respuesta del geólogo. Hay que reportar también el MAE sin marcas (9.9) como cifra principal.
- Sin intervalos de confianza, sin Bland-Altman todavía, sin línea base de variación entre geólogos.
- No hay licencia en el repo (CV dijo en #questions que "cualquier licencia source-available sirve", pero hay que poner una).

Qué lo sube:
- Cifra principal honesta: MAE sin marcas, con intervalo de confianza por bootstrap.
- Comparar contra la variación entre geólogos que reporta la literatura. Si el error de CoreSight cae dentro de esa variación, ese es el titular.
- Publicar en el repo `outputs/eval/` y `outputs/describe/` (sin datos del Kaggle NC; solo métricas y figuras).

### Demo (25%): 6 de 10

Evidencia a favor:
- Carga rápida (la caja de muestra sale en menos de 10 s por la caché), diseño cuidado, funciona en móvil.
- Overlays claros (natural, dudosa, mecánica), registro por tramo, "el geólogo conservó 32 de 32 valores".

Evidencia en contra (los primeros 30 segundos de un juez):
- La portada no tiene imagen: no se ve una caja ni el antes y después. El juez lee tres tarjetas de texto.
- "Try a sample box" abre roca excelente. No hay nada que corregir ni que alertar. El "aha" no llega.
- No hay agentes ni handoffs visibles (día 8 pendiente).
- En móvil el botón "Approve" queda cortado en el encabezado.
- No sabemos qué pasa si un juez sube una foto que no es una caja. Hay que probarlo.
- Todavía no hay video, y el video pesa en Demo y en toda la final.

Qué lo sube:
- Una muestra "dramática" como primera opción: roca mala y sulfuros visibles, para que se disparen la alerta de seguridad y la solicitud de ensayes.
- Portada con la foto de una caja y el registro saliendo encima (aunque sea una animación de 3 segundos).
- Video de 3 minutos con voz en off en inglés y subtítulos (CV recomendó inglés porque los jueces hablan inglés).

### Nota ponderada

| Criterio | Peso | Hoy | Con los cambios |
|---|---|---|---|
| Impacto | 30% | 6 | 8 |
| Uso de Meta | 25% | 7 | 8.5 |
| Técnica | 20% | 7.5 | 8.5 |
| Demo | 25% | 6 | 9 |
| **Total** | | **6.5** | **8.5** |

---

## 3. Riesgos de descalificación o de no pasar la primera ronda

| Riesgo | Probabilidad | Qué lo dispara | Mitigación |
|---|---|---|---|
| "Simple image analyzer" (anti-proyecto) | Media | Hoy la demo es literalmente: subo foto, sale un análisis. Si el video abre igual, se lee como analizador de imágenes | Abrir el video con el flujo completo: foto, geólogo corrige, agentes generan borradores para 4 áreas. Decir "registro geotécnico de producción, no un clasificador de imágenes" |
| Trabajo previo presentado como nuevo | Media | `geometry.py` (RQD, TCR, FF, unión de roturas mecánicas) y su test son del 25 oct y no han cambiado. El pitch lo llama el motor central | Ya está marcado en el README. Falta: (1) una línea al inicio del video que diga qué era previo, como pide el FAQ de CV; (2) que el video no presuma la fórmula del RQD como logro del hackathon, sino lo nuevo: calibración, SAM, roturas por marcas, revisión, voz, agentes; (3) Connor (Meta) confirmó que la aclaración en el README basta |
| Commits del 26 oct | Baja | La guía dice "Building period: Oct 27 to Nov 4" | Las reglas oficiales dicen 26 oct a 4 nov y el primer commit de código es posterior al kickoff (16:43 UTC vs 16:00 UTC). CV no objetó casos iguales en #questions. No hacer nada |
| Muse Code prometido y no usado | Media (credibilidad, no descalificación) | Repo público con todos los commits firmados por Claude y registro vacío | Usar Muse Code de verdad en el día 8 y documentarlo. No reescribir historia de git. En el README: "construido con Claude Code y Muse Code", honesto |
| Datos sin derechos | Baja | El Kaggle es NC | Ya está fuera del repo y de la imagen. Mantener: solo métricas, nunca fotos del Kaggle en el video ni en la demo |
| Demo caída o sin créditos durante el juzgado (5 al 9 nov) | Media | Límite de 20 análisis por hora compartido, créditos de Meta, VPS compartido | Precalentar la caché de todas las muestras, monitorear saldo, tener un video de respaldo del flujo, y probar que una foto mala da un error claro |
| Falta de licencia | Baja | No hay `LICENSE` | Agregar MIT o Apache-2.0 |

---

## 4. Impacto e historia

### A quién beneficia
- **Geólogo de logueo** (usuario directo): menos horas midiendo piezas con flexómetro, menos subjetividad.
- **Geotecnia y seguridad**: la clase de roca mala llega el mismo día a quien diseña el soporte del túnel.
- **Laboratorio y planta**: saben antes qué intervalos ensayar y qué mineral viene.
- **Finanzas y dirección**: costo del ensaye y trazabilidad para auditorías (NI 43-101, JORC).

### Cuánto vale (por confirmar con fuentes antes del video)
Datos que hay que buscar y citar, no inventar:
- Presupuesto global de exploración (S&P Global publica la cifra anual).
- Metros de barrenación diamantina al año en México y en el mundo.
- Tiempo típico de logueo geotécnico por caja y costo de un geólogo por día.
- Un caso de falla de terreno o dilución por mala clasificación de roca.

Si no se consiguen fuentes, usar el caso propio: "un geólogo tarda X minutos por caja, una campaña mediana tiene Y cajas". Pedir X y Y a un geólogo real.

### Cómo se cuenta en 3 minutos

| Tiempo | Qué se ve | Qué se dice |
|---|---|---|
| 0:00 a 0:10 | Línea de trabajo previo en pantalla | "Antes del hackathon: el esqueleto y la fórmula de RQD. Todo lo demás se construyó esta semana" |
| 0:10 a 0:30 | Un geólogo con una caja real, flexómetro en mano | El problema, con un número |
| 0:30 a 1:20 | Foto de celular, la caja se calibra, SAM corta las piezas, sale el RQD por tramo | "Los modelos de Meta perciben, el código calcula" |
| 1:20 a 1:50 | El geólogo da clic en una pieza mal cortada y dicta una corrección por voz | "El geólogo decide" |
| 1:50 a 2:30 | Aprobar la caja: Wonder reparte a 4 agentes; borradores de ensaye, alerta de terreno, aviso a planta y costo; cada uno con su botón de aprobar | "Del núcleo a toda la mina, con un humano en cada paso" |
| 2:30 a 2:50 | Tabla de evaluación y "modo sin internet" con Glimmer | Credibilidad técnica y modelo abierto |
| 2:50 a 3:00 | Logo, URL, Zacatecas | Cierre |

---

## 5. Competencia vista en Discord y huecos

Lo que construyen otros en Push the Frontier:
- **ANTS**: robot que aprende una tarea con una demostración (SAM 3.1, Muse Wonder y Muse Spark).
- **BlinkFlow**: agente que depura simuladores de robots; usa SAM 3.1, Wonder, Muse Code SDK dentro del producto y Glimmer local con manifiesto de procedencia.
- **MuseForge**: Spark genera controladores ROS 2 y mejora con fallas en simulación.
- **A.N.K.I.T.A** y **Cleanroom**: agentes de computadora con compuertas de aprobación y seguridad de Muse Code (Agents Rule of Two de Meta).
- Agente de pruebas de hardware con Arduino y SAM 3.1.
- Un robot de mesa que busca objetos con SAM 3.1 (Startups).

Lectura:
- **Nadie hace minería ni geología.** Es nuestro mayor diferenciador y hay que nombrarlo.
- Los fuertes usan **varios modelos de Meta en ciclo cerrado** (percibe, decide, actúa, verifica) y **Muse Code dentro del producto**. BlinkFlow ya piensa en procedencia para el premio de modelos abiertos.
- Muchos equipos no tienen créditos ni tarjeta y dependen de un solo proveedor. Tener tres backends funcionando ya es ventaja.
- Patrón que se repite: "aprobación humana antes de actuar". No basta para distinguirse; hay que mostrar autonomía real en lo que sí se automatiza (enrutar, priorizar, calcular costo) y verificación determinista.

Huecos nuestros frente a ellos:
1. No mostramos un ciclo que se cierre (las correcciones no mejoran nada todavía).
2. No usamos Muse Code en el producto ni en el desarrollo.
3. No tenemos manifiesto de procedencia publicado para Glimmer.
4. No mencionamos la "Agents Rule of Two" de Meta, que encaja con los agentes del día 8.

---

## 6. Premios extra

Se pueden ganar varios a la vez (no hay regla en contra; la pregunta en #office-hours sigue sin respuesta).

| Premio | Monto | Posibilidad hoy | Qué hacer |
|---|---|---|---|
| Best Build on Meta Open Weight Models | $10K | Media-alta | Publicar en el repo el manifiesto de cada corrida de Glimmer y de Spark Open (modelo, cuantización, hardware, tokens, tiempo, hash de la salida). Connor (Meta) pidió "tanta procedencia como se pueda" y capturas. Grabar 20 s de Glimmer corriendo con el Wi-Fi apagado. Si da tiempo, LoRA o few-shot con las correcciones del geólogo |
| Best Agentic Use-Case | $5K | Media | Que el orquestador decida de verdad (no reglas fijas), que los agentes usen herramientas (geometry, precios, historial del barreno), que haya verificación determinista de cada borrador y un registro de decisiones visible. Citar la Agents Rule of Two. Ver Agents 102 antes de construir |
| Most Viral Project | $20K | Baja | La viralidad en X depende de la audiencia. Lo realista: un clip vertical de 30 a 45 s con el "antes y después" de la caja, publicado el 4 nov temprano, con hilo en español e inglés, y pedirle a la red de AnaliZac, a geólogos y a la UAZ que lo compartan. Raúl publica; nosotros solo dejamos el borrador |
| Community Vote | $10K | Baja-media | Abre el 9 nov. Preparar un mensaje corto para grupos de geología y minería de México y LatAm (Raúl lo envía). El nicho minero mexicano es comunidad unida: puede rendir más de lo esperado |
| Best Creative Build | $5K | No aplica | No perseguir |

---

## 7. Cambios priorizados

Orden: alto impacto y poco esfuerzo primero.
Días del plan: 8 (agentes), 9 (evaluación), 10 (video y README), 11 (envío).
Como vamos 4 días adelantados, los días 8 a 10 caben antes de su fecha y queda colchón real.

| # | Cambio | Por qué sube la nota | Esfuerzo | Día |
|---|---|---|---|---|
| 1 | **Muestra dramática en la demo**: una caja pública con roca mala y sulfuros visibles (buscar en Commons con licencia libre), o mejor una caja real de una mina de Zacatecas fotografiada con permiso. Que sea la primera muestra | Demo e Impacto. Sin esto los agentes no tienen qué disparar | 2 a 6 h (más el permiso) | 8, antes de los agentes |
| 2 | **Publicar la evidencia**: sacar de `.gitignore` las métricas de `outputs/eval/` y `outputs/describe/` (sin fotos del Kaggle), actualizar el README (quitar "Early scaffold", llenar Evaluation) y agregar `LICENSE` | Técnica y Open Weights. Hoy un juez que abre el repo no ve resultados | 1 a 2 h | 8 (hoy mismo) |
| 3 | **Muse Code de verdad**: construir con Muse Code al menos un agente del día 8 o la verificación de borradores, con capturas y commits listados en `APPLICATION.md` y el README | Cumple lo prometido; Uso de Meta | 0 h extra (es trabajo que ya toca) | 8 |
| 4 | **Agentes con autonomía verificable**: Wonder decide qué áreas aplican y por qué; agentes con herramientas (geometry, tabla de precios de ejemplo, historial); un verificador determinista revisa cada borrador antes de mostrarlo; registro de decisiones en la UI | Agentic, Uso de Meta y aleja el "image analyzer" | Lo ya planeado más 2 h | 8 |
| 5 | **SAM 3.1 con prompt de punto en la revisión**: clic en una pieza y SAM la vuelve a segmentar en ese punto | El "nos sorprendió" del criterio de Meta; muy visual en el video | 4 a 6 h (validar primero que la API acepta prompts de punto) | 8 o colchón |
| 6 | **Manifiesto de procedencia** para Glimmer y Spark Open, publicado en el repo, y un clip de Glimmer corriendo sin red | Premio Open Weights ($10K) | 2 h | 9 |
| 7 | **Evaluación honesta**: cifra principal sin marcas del geólogo, intervalo de confianza, Bland-Altman, comparación con la variación entre geólogos de la literatura, casos de falla con foto | Técnica; blinda contra el juez escéptico | Lo ya planeado | 9 |
| 8 | **Números de impacto con fuente** y, si se puede, 15 s de un geólogo real | Impacto (30%), el criterio que más pesa | 2 a 4 h de búsqueda y una llamada | 9 |
| 9 | **Portada con imagen** (caja con overlays, antes y después) y arreglar el encabezado en móvil | Primeros 30 s del juez | 1 a 2 h | 10 |
| 10 | **Prueba de abuso**: subir una foto que no es caja, una foto enorme, una caja sin escala; confirmar errores claros. Precalentar la caché de todas las muestras y vigilar créditos | "Aguanta en producción" (Startups) | 1 h | 10 |
| 11 | **Cerrar el ciclo de aprendizaje**: few-shot o LoRA de Glimmer con las correcciones guardadas, medido antes y después | Uso de Meta y Open Weights; historia de producto | 1 a 2 días; solo si los puntos 1 a 10 están hechos | Colchón (31 oct a 2 nov) |
| 12 | **Clip vertical y borrador de post en X** (español e inglés), y mensaje para Community Vote | Premios Viral y Community | 2 h | 10 |

Si falta tiempo, recortar en este orden: 11, 5, 12. Nunca 1, 2, 4 ni 7.

---

## 8. Lo que NO hay que cambiar

- **La arquitectura neurosimbólica.** Es la mejor respuesta al juez escéptico. El LLM sigue sin calcular el RQD.
- **El track Startups.** Cambiarse a Indie no da ventaja clara y la aplicación ya dice Startups.
- **El alcance de áreas.** Laboratorio, seguridad, planta y finanzas bastan. Nada de mantenimiento ni operaciones en código.
- **Los tres backends de descripción.** Ya están; no sumar Fireworks ni Modal salvo que se haga el LoRA.
- **Muse Image.** No aporta al problema.
- **La revisión humana obligatoria.** Es parte del valor, no una limitación.
- **El diseño visual de la página.** Ya está a nivel de producto; solo la portada y el encabezado en móvil.
- **El día 10 completo para el video.** El video decide la final.
- **Reescribir la historia de git** para quitar las firmas de Claude. Sería peor si se nota; la respuesta es usar Muse Code de verdad y decirlo.

---

## 9. Preguntas que Raúl puede llevar a #office-hours

Solo él publica. Borradores para que decida:
- "Our deterministic RQD engine (one file) was written the day before kickoff and is marked in the README. Is a README note plus a line at the start of the video enough, or should we move it to a separate library?"
- "Does SAM 3.1 on the Model API accept point prompts (click coordinates), or only text prompts?"
- "For the Open Weights prize, is a run manifest in the repo plus a screen recording of Muse Glimmer running offline enough provenance?"
