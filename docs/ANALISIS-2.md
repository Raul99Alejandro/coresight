# Segundo análisis adversarial de CoreSight (27 oct, noche)

Punto de vista: un juez de Meta que ve 3 minutos de video, abre el repo 5 minutos y prueba la demo con las muestras públicas.
Pregunta de Raúl: el sistema quedó sencillo, no sobresale y el alcance se achicó por ir rápido. Confirmar o desmentir con evidencia y decir cómo subir el nivel.

Fuentes:
- La app local en `main` (`4ed1ee8`), recorrida de punta a punta el 27 oct con la muestra de Nevada U12G y dos fotos que no son cajas.
- https://coresight.analizac.com (sigue en `814a154`: solo Onkalo, sin agentes ni Nevada).
- `docs/ANALISIS.md`, `PLAN.md`, `KICKOFF.md`, `APPLICATION.md`, `IMPACT.md`, `PROVENANCE.md`, `README.md`, `outputs/eval/report.md`, `src/coresight/`, `docs/muse-code/`.
- Documentación de modelos en https://dev.meta.ai/docs/ (SAM, Spark, Wonder, Glimmer, Muse Code, precios).
- Página del hackathon en Cerebral Valley. La sección `/details` carga con JavaScript y no se pudo leer sin sesión. No hay galería pública de otros equipos visible hoy.

Capturas en `docs/analisis-2/`.

---

## 1. Veredicto corto

Raúl tiene razón a medias.

- **Lo que no es cierto:** el alcance no se achicó. Todo lo prometido en la aplicación está hecho y se agregó más (Wonder, 4 agentes, verificador con Muse Code, 3 backends de descripción, procedencia con hashes, evaluación con bootstrap). Por dentro el sistema es más serio que la mayoría de los proyectos de hackathon: 188 tests en verde, cada número trazable a `geometry.py`, errores publicados con honestidad.
- **Lo que sí es cierto:** lo que un juez *ve* es sencillo. La unidad del producto es una foto y la salida es una tabla. Cada modelo de Meta se usa una vez y en su forma más básica (SAM con la palabra "stone", Spark que describe un recorte, Wonder que aplica cuatro reglas escritas en su prompt). Hay una sola caja, un solo agente que se dispara y ningún momento en que el sistema haga algo que una persona no esperaba.
- **Lo que preocupa más:** la prueba de abuso falla. Una captura de una página web sale como "RQD 100 %, Excellent". Para el track Startups, que se juzga por "whether it holds up in production", eso pesa más que cualquier función nueva.

Calificación ponderada hoy: **6.8**. Con el plan de la sección 6: **8.2 a 8.6**.

---

## 2. Prueba como juez: lo que encontré

### 2.1 Recorrido

| Paso | Resultado | Lectura del juez |
|---|---|---|
| Portada | Título, dos botones y tres tarjetas de texto. Sin imagen de caja ni antes y después ([01-portada.jpg](analisis-2/01-portada.jpg)) | "Otro analizador de fotos". El cambio 9 del primer análisis sigue pendiente |
| "Try a sample box" | Abre Nevada U12G de inmediato (caché). Overlays claros, 5 roturas para revisar ([02-nevada-revision.jpg](analisis-2/02-nevada-revision.jpg)) | Bien. Se ve producto |
| Revisar una rotura | El panel del tramo abre, cambio dudosa a mecánica, RQD sube de 22.7 a 26.7 con "after your edits" y el valor original tachado ([03-correccion.jpg](analisis-2/03-correccion.jpg)) | El mejor momento de la demo. "Code calculates" se entiende |
| Corrección | Es una lista de 14 piezas con menús. No se corrige tocando la foto | Funciona, pero es una hoja de cálculo. No hay interacción con un modelo |
| Aprobar | El diálogo no avisa que se van a lanzar agentes | Se pierde el momento |
| Agentes | Unos 50 s. Mientras tanto se ve JSON crudo (`run_metrics({"run": 2}) → {"rqd_pct": ...`). Wonder decide: solo seguridad aplica. Spark redacta la alerta y `verify.py` pasa 4 de 4 ([04-agentes.jpg](analisis-2/04-agentes.jpg)) | La verificación es buena idea y se ve. El texto dice "Run 0", "rqd_pct 26.7", "tcr_pct 53.1": se lee como log de depuración. 3 de 4 tarjetas dicen "Not needed" |
| Borrador de seguridad | "Run 0: Deere class poor, RQD 26.7 ... Check support and scaling." repetido por tramo | Una plantilla con números. Un juez dice "esto es un if" |
| CSV | `log.csv` y `corrections.csv` correctos, con la corrección, el original y la fuente | Bien |
| Foto que no es caja | Subí `outputs/models_glyphs.png` (captura de nuestra propia guía visual). Calibración "encontró 5 filas", SAM devolvió 22 piezas con confianza 0.00, `geometry.py` dio **RQD 100 %, Excellent**. Solo Spark dijo "No rock visible" con confianza 1.0, y nada lo usó ([05-abuso-no-es-caja.jpg](analisis-2/05-abuso-no-es-caja.jpg)) | Falla de producción. Es justo el caso que el juez escéptico prueba primero |
| Móvil | El nombre de la caja ocupa 3 líneas en el encabezado ([06-movil.jpg](analisis-2/06-movil.jpg)) | Detalle, pero el cambio 9 no entró |
| Demo desplegada | Sigue en `814a154`. Ni Nevada, ni agentes, ni evaluación nueva | Si un juez entra hoy ve la versión vieja |

### 2.2 Errores concretos

1. **No hay compuerta de entrada.** Calibración, SAM y geometría aceptan cualquier imagen. Spark ya sabe decir que no es roca, pero esa señal no detiene nada. `api.py:369`, `review.analyze`.
2. **Crédito de foto equivocado.** El pie de cada caja dice "Sample photo by Kallerna, Wikimedia Commons, CC BY-SA 4.0" aunque sea Nevada (dominio público, DOE) o una foto subida. Está fijo en `web/index.html:875`. Un juez que cuida licencias lo nota; además es un error de atribución.
3. **Subir una caja no deja elegir filas.** El formulario no tiene campo de filas y `Job.n_rows` queda en 5. Nevada necesitó 4. Una caja de 3, 4 o 6 filas subida por un juez sale mal.
4. **La muestra principal da un número muy lejos de la etiqueta sin corregir.** Tramo 3 de Nevada: 34 % contra 80.8 % de nuestra etiqueta. Si el juez aprueba sin corregir, la alerta de seguridad llama "poor" a roca buena. Sirve para la historia "el geólogo corrige", pero solo si el video lo muestra.
5. **El diálogo de aprobar borrador se queda abierto** al navegar a otra caja (lo vi sobre la caja de prueba).
6. **Texto de agentes con nombres de campo y tramos desde 0.** Ya estaba anotado el 27 oct en la nota del día 8 y sigue igual.
7. **La traza pública de Muse Code dice `"model": "muse-spark-1.3-contributor"`** aunque el comando lleva `--contributor-mode off` (`docs/muse-code/verify-1.json:5`). Un juez de Meta lo puede leer como que no se entendió el modo o que el registro no es confiable. Hay que explicarlo en el README o resolverlo.
8. **"35 of 35 pieces kept" contra "34 pieces"** en la tabla de modelos de la misma caja. Pequeño, pero es el tipo de inconsistencia que hace dudar de los números.

### 2.3 Lo que sí sorprende

- La tabla "Models in this box" con tiempo, llamadas, caché y costo por modelo, y "the geologist kept 75 of 76 values".
- El RQD tachado y recalculado por `geometry.py` al corregir.
- `verify.py` mostrado como 4 checks con palomita bajo cada borrador.
- Spark notó solo la muestra encerada y la zona de núcleo triturado y lo puso en anomalías. Eso es útil y no se presume en ninguna parte.

---

## 3. Los 12 cambios del primer análisis

| # | Cambio | Estado | Calidad | Comentario |
|---|---|---|---|---|
| 1 | Muestra dramática | Parcial | 5/10 | Nevada U12G es roca mala de verdad. Pero no hay sulfuros, así que laboratorio, planta y finanzas nunca se disparan en la demo. Y las dos fuentes son sitios nucleares (Onkalo repositorio, Nevada sitio de pruebas), no minas. La historia de Zacatecas sigue sin una caja de mina |
| 2 | Evidencia pública | Hecho | 9/10 | `outputs/eval` y `outputs/describe` en git, README con resultados, LICENSE Apache-2.0 |
| 3 | Muse Code de verdad | Hecho | 6/10 | Honesto y con trazas. Pero es un archivo de 159 líneas, la sandbox no corrió tests y la traza dice "contributor". Un juez lo lee como "lo usaron para cumplir" |
| 4 | Agentes con autonomía verificable | Hecho | 6/10 | Arquitectura buena (herramientas de solo lectura, verificador, Rule of Two, registro). Pero las reglas de ruteo están escritas en el prompt (`agents.py:268`), así que Wonder hace lo que haría un `if`. Textos con nombres de campo. 50 s de espera |
| 5 | SAM con prompt de punto | No hecho | - | La doc confirma el formato (sección 5). Se hizo "Split" manual, que resuelve el error pero no usa a SAM |
| 6 | Procedencia de modelos abiertos | Hecho | 9/10 | Hashes iguales a Hugging Face, comando, hardware, tokens. Falta grabar el clip sin red |
| 7 | Evaluación honesta | Hecho | 9/10 | Titular sin marcas, bootstrap por caja, Bland-Altman, casos de falla con foto. Es lo más fuerte del repo para un juez técnico |
| 8 | Números de impacto | Parcial | 7/10 | Fuentes abiertas y marcadas. Falta el geólogo real, que es lo que más mueve Impacto |
| 9 | Portada con imagen y móvil | No hecho | - | Ver 2.1 |
| 10 | Prueba de abuso | No hecho | - | Y falla (2.2, punto 1) |
| 11 | Ciclo de aprendizaje | No hecho | - | Las correcciones se guardan pero no cambian nada |
| 12 | Clip y post | No hecho | - | Es del día 10 |

---

## 4. Calificación por criterio

Juez escéptico, 3 minutos de video y 5 de repo. Supongo un video bien hecho con lo que existe hoy.

| Criterio | Peso | Hoy | Por qué | Esperada con el plan |
|---|---|---|---|---|
| Impacto | 30% | 6.5 | Problema real con números de Camimex y fuentes. Pero no hay geólogo, no hay mina, las muestras son de sitios nucleares y el producto termina en una caja. Un juez no ve cómo cambia una campaña de barrenación | 7.5 (8 con geólogo o caja real) |
| Uso de Meta | 25% | 7 | Siete piezas de Meta, más que casi cualquiera. Pero cada una en modo básico. Ningún modelo le habla a otro. No sorprende | 8.5 |
| Demo | 25% | 6 | Página cuidada, pero portada sin imagen, versión desplegada vieja, una foto de una web sale como roca excelente, y el clímax (agentes) es un borrador de plantilla tras 50 s | 8.5 |
| Técnica | 20% | 8 | 188 tests, evaluación con IC, procedencia, verificador, separación modelo/código. Le resta la falta de compuerta de entrada | 8.5 |
| **Total** | | **6.8** | | **8.2 a 8.6** |

### Qué haría que lo descarten como "simple image analyzer"

1. El video abre con "sube una foto, sale una tabla".
2. Todo pasa en una sola caja. No hay barreno, ni tendencia, ni decisión que dependa de varias cajas.
3. Los agentes parecen reglas: 3 de 4 dicen "Not needed" y el que aplica repite una plantilla.
4. El juez sube cualquier imagen y el sistema le da un RQD.
5. Ningún modelo se usa de forma interactiva o encadenada: SAM recibe una palabra, Spark un recorte, Wonder unas reglas.

Lo que lo aleja: mostrar que CoreSight **entiende un barreno completo**, que **los modelos se corrigen entre sí y con el geólogo**, y que **dice "no" cuando no debe medir**.

---

## 5. Lo que Meta ofrece y no usamos

Revisado en https://dev.meta.ai/docs/ el 27 oct.

| Capacidad | Doc | Uso en CoreSight | Valor |
|---|---|---|---|
| **SAM 3.1 con prompts de punto y caja** | [/docs/sam/segmenting](https://dev.meta.ai/docs/sam/segmenting) | Clic del geólogo sobre una pieza y SAM la vuelve a cortar; cajas de Spark como prompt | Alto |
| **Spark con localización** (puntos y cajas en cuadrícula 0 a 1000, hasta 50 imágenes por llamada) | [/docs/image-understanding](https://dev.meta.ai/docs/image-understanding) | Spark marca filas, tarjetas, muestras enceradas y bloques de tramo; esas cajas se pasan a SAM | Alto |
| **Spark con video y audio** | [/docs/video-understanding](https://dev.meta.ai/docs/video-understanding) | El geólogo filma la caja y la narra; una llamada da descripción y dictado | Medio, riesgoso |
| **SAM 3.1 con video** (`input_video`, $0.20 por 1000 cuadros, mínimo 50) | [/docs/sam/segmenting](https://dev.meta.ai/docs/sam/segmenting) | Recorrer la charola con el celular | Bajo para el tiempo que queda |
| **Prompt caching** (entrada en caché $0.15/M contra $1.25/M) | [/docs/prompt-caching](https://dev.meta.ai/docs/prompt-caching) | Prompt fijo de descripción y de agentes. Un número de costo más en la tabla de modelos | Bajo, barato |
| **Respuestas en segundo plano** (`background: true`) | [/docs/pricing-rate-limits](https://dev.meta.ai/docs/pricing-rate-limits) | Procesar un barreno de varias cajas | Medio, si se hace la vista de barreno |
| **Muse Code headless** (`muse exec --json`) | [/docs/muse-code/extending](https://dev.meta.ai/docs/muse-code/extending) | Ver sección 8 | Medio |
| **Post-entrenamiento de Glimmer** (LoRA/QLoRA con Axolotl o TRL; QLoRA en 1 H100; Unsloth en unos 24 GB) | [/docs/muse-glimmer/post-training](https://dev.meta.ai/docs/muse-glimmer/post-training) | Ciclo de aprendizaje con correcciones | Alto en papel, pero sin datos propios suficientes (sugiere unos 500 ejemplos) |

Formato de prompts en SAM 3.1, según la doc: van como tokens dentro de `input_text`, junto a `input_image`, con `"stream": true`.
Caja: `<0f>1<|box;x1=444;y1=626;x2=675;y2=849;w=1800;h=1200|>`. Punto positivo: `<|point;x=1430;y=700;w=1800;h=1200|>`; negativo con `-` delante.
Hasta 16 objetos separados por comas. `w` y `h` deben ser el tamaño de la imagen o la API da 400. No se mezcla una frase ("stone") con puntos o cajas en la misma solicitud.
Hay que probarlo con la API real antes de construir encima (regla del repo).

Meta no ofrece embeddings, TTS, modelos de profundidad ni 3D, ni fine-tuning dentro de la API.
Por eso un "modelo 3D" tendría que salir de nuestra geometría, no de un modelo de Meta.

---

## 6. Propuestas para los días que quedan

Hoy es 27 oct en la noche. Quedan 28 oct a 2 nov para construir (6 días; el 2 nov se congela).
Día 10 (3 nov) completo para el video. Entrega 4 nov antes de las 18:00.

### 6.1 Pensar en grande

Lo que haría a CoreSight memorable no es otra función sobre una caja. Es cambiar la unidad del producto de **una foto** a **un barreno**, y que los modelos de Meta **trabajen encadenados y se corrijan**:

1. El geólogo sube las cajas de un barreno. CoreSight arma el registro continuo por profundidad (columna de RQD, litología, zonas de falla) y una vista 3D del barreno.
2. Spark localiza lo que no es núcleo (tarjetas, bloques, muestras enceradas) y se lo pasa a SAM como cajas; SAM corta; el geólogo hace clic donde SAM falló y SAM vuelve a cortar con ese punto.
3. Un agente de barreno ve la tendencia entre cajas ("el RQD cae de 80 a 20 entre 12 y 15 m, posible zona de falla") y propone una acción con su verificación.
4. Cada corrección del geólogo mejora la siguiente caja, medido.
5. Todo puede correr en la mina sin internet.

### 6.2 Aterrizado: propuestas priorizadas

| # | Propuesta | Valor para la rúbrica | Costo | Riesgo | Día sugerido | Qué se corta a cambio |
|---|---|---|---|---|---|---|
| A | **Compuerta de entrada y arreglos de producción**: rechazar fotos sin caja con tres señales (confianza de calibración, confianza de SAM, un campo `is_core_tray` de Spark validado con Pydantic), mensaje claro; crédito de foto por muestra; campo de filas al subir; diálogo que no se queda abierto; tramos desde 1 y sin nombres de campo en textos de agentes; desplegar días 8 y 9 hoy | Técnica y Demo. Quita el peor hallazgo. Es "holds up in production" | 0.5 día | Bajo | 27 noche y 28 | Nada. Obligatorio |
| B | **Spark localiza, SAM corta**: Spark devuelve cajas de filas y de lo que no es núcleo (tarjetas, cera, bloques); se pasan a SAM 3.1 como prompts de caja en lugar de "stone". Medir con la misma evaluación (ablación nueva `spark+sam`) | Uso de Meta (dos modelos encadenados, el uso que la doc presume) y Técnica (una fila más en la ablación, con IC). Ataca la falla real de Nevada | 1 día | Medio: hay que validar el formato con la API y que mejore el MAE. Si no mejora, se publica igual como ablación honesta | 28 y 29 | Nada si cabe; si no, recortar C a solo punto positivo |
| C | **SAM con clic en la revisión**: el geólogo toca la foto donde falta o sobra una rotura; SAM vuelve a segmentar esa fila con punto positivo o negativo; `geometry.py` recalcula; la corrección queda con fuente "sam-point" | Demo (el momento visual del video) y Uso de Meta (SAM interactivo, para lo que existe). Mantiene "Split" como respaldo | 1 día | Medio: latencia de SAM por clic; si es lenta, se muestra en video y la UI conserva el Split manual | 29 | Nada |
| D | **Vista de barreno (hole view)**: varias cajas del mismo barreno en una columna continua por profundidad con RQD, TCR, FF, clase de Deere y litología; zonas resaltadas; vista 3D simple del barreno (cilindro coloreado por RQD, three.js) con nota de que la traza es de ejemplo si no hay levantamiento. Datos públicos: Onkalo cajas 5 y 6 (mismo barreno) y U12G cajas 1 y la de 19.0 a 26.3 ft (`commons_nts_u12g_2.jpg`, mismo barreno). Explorar la serie completa de geoloogia.info (Estonia) si la licencia por archivo se confirma | Impacto (de caja a campaña), Demo (imagen fuerte para el video), y aleja "image analyzer" | 1.5 días | Medio: pocas cajas públicas por barreno. La agregación por profundidad es cálculo geotécnico y va en `geometry.py` con tests | 30 y medio 31 | Correlación entre barrenos: no hay datos públicos. Queda como visión en el video |
| E | **Agente de barreno**: corre al aprobar cada caja con el historial del barreno; detecta tendencias con herramientas deterministas (caída de RQD, cambio de litología entre cajas) y propone una acción: "pedir núcleo orientado", "avisar a geotecnia antes del siguiente tramo". Sacar las reglas fijas del prompt del orquestador: que Wonder decida con el historial y que `verify.py` revise | Agentic ($5K) y Uso de Meta. Con D, planta deja de decir siempre "Not needed" | 0.5 a 1 día | Medio: Wonder lento (50 s hoy). Mostrar el progreso con frases, no JSON | 31 | El agente de finanzas queda igual, sin mejoras |
| F | **Ciclo de aprendizaje medido (sin LoRA)**: (1) las correcciones de roturas ajustan los umbrales del perfil de intensidad y de "dudosa" por sitio, con validación cruzada por caja y el MAE antes y después; (2) las correcciones de descripción entran como ejemplos few-shot para Spark y Glimmer. Una gráfica: "después de N correcciones, el error baja de X a Y" | Uso de Meta, Open Weights y la historia de producto | 1 día | Alto: con pocas cajas el efecto puede no ser significativo. Si no baja, no se presume; queda como "listo para aprender" | 1 nov (timebox 6 h) | LoRA de Glimmer. No hay datos propios suficientes y entrenar con el Kaggle NC choca con su licencia |
| G | **Portada con imagen y guion de demo dentro del producto**: la portada muestra una caja con overlays que se dibujan y la vista de barreno; un botón "Recorrido de 60 s" que lleva por muestra, corrección, aprobación y agentes | Demo, primeros 30 s | 0.5 día | Bajo | 1 nov | El clip vertical se hace con material del video, no aparte |
| H | **Caja de mina real** (Zacatecas, con permiso), procesada con Glimmer local o con los créditos gratis apagados, y 15 s de un geólogo | Impacto, el criterio que más pesa | Llamadas de Raúl | Alto (depende de terceros) | En paralelo, cierre 1 nov | Nada de código |
| I | **SAM local sin internet**: probar si hay pesos abiertos de SAM 3.x que corran en la RTX 3070 Ti. Si sí, el flujo completo (SAM + geometry + Glimmer) corre en la mina sin red | Open Weights ($10K) y la frase "todo corre en la mina" | Spike de 3 h; 1 día si funciona | Alto: no confirmé pesos de SAM 3.1 ni licencia | Solo si A a E están listos, 1 nov | Se queda en el video como visión si no da |
| J | **Video con audio del geólogo** (Spark video + dictado) | Uso de Meta | 1 día | Alto | No | Cortado |
| K | **Correlación entre barrenos y modelo geológico 3D** | Impacto en papel | 3 días o más | Muy alto, sin datos públicos | No | Visión en el video |

### 6.3 Lo que no hay que hacer

- No entrenar ni hacer LoRA con el Kaggle NC.
- No inventar una traza de barreno como real: si la vista 3D usa azimut y echado de ejemplo, que lo diga en pantalla.
- No mandar fotos privadas por créditos gratis.
- No quitar el "Split" manual: es el respaldo si SAM con clic falla.
- No sumar Muse Image ni otro proveedor.

---

## 7. Plan revisado

| Fecha | Objetivo | Listo cuando |
|---|---|---|
| lun 27 oct, noche | Desplegar días 8 y 9; crédito de foto por muestra; tramos desde 1 y sin nombres de campo en agentes | La URL pública muestra Nevada y agentes |
| mar 28 oct | A completo. Ver Agents 102 a las 10:00. Probar el formato de cajas y puntos de SAM con la API real (foto pública) | Una web, una selfie y una caja sin escala dan error claro, con test. Smoke test de SAM con caja y con punto |
| mié 29 oct | B (Spark localiza, SAM corta) y C (clic en la revisión) | Ablación `spark+sam` en `outputs/eval`; clic en Nevada tramo 2 corrige como hoy lo hace Split |
| jue 30 oct | D: vista de barreno con Onkalo 5+6 y U12G 1+3. Taller de Fireworks a las 10:00 (solo como insumo para F) | Columna por profundidad y 3D simple; agregación en `geometry.py` con tests |
| vie 31 oct | E: agente de barreno y orquestador sin reglas fijas; progreso legible | Una caja aprobada dispara una alerta de tendencia verificada |
| sáb 1 nov | F (timebox), G, prueba de abuso completa, caché precalentada, desplegar. Cierre de H | Gráfica antes y después o nota honesta; portada nueva en producción |
| dom 2 nov | Congelar código. Ensayar el flujo completo 3 veces. Grabar clip de Glimmer sin red y tomas crudas de la demo | Nada nuevo entra. Lista de tomas completa |
| lun 3 nov | Día 10: video con HyperFrames, voz en inglés, subtítulos. README final | Video de 3 min exportado |
| mar 4 nov | Envío antes de las 18:00. Premios Open Weights, Agentic y Viral. Borradores del post para Raúl | Enviado |

Orden de recorte si falta tiempo: I, F, E (dejar solo "sin reglas fijas"), D sin 3D. Nunca A, B ni C.

Guion del video ajustado (cambia la sección 4 del primer análisis):

| Tiempo | Qué se ve |
|---|---|
| 0:00 a 0:10 | Línea de trabajo previo |
| 0:10 a 0:25 | El problema con un número y, si se consigue, el geólogo |
| 0:25 a 0:40 | Alguien sube una captura de pantalla y CoreSight dice que no es una caja. "It knows when not to measure" |
| 0:40 a 1:20 | Una caja: Spark marca tarjetas y cera, SAM corta con esas cajas, `geometry.py` da el RQD |
| 1:20 a 1:50 | El geólogo toca la foto, SAM vuelve a cortar, el RQD se recalcula |
| 1:50 a 2:20 | Se aprueban varias cajas y aparece el barreno en 3D; el agente de barreno marca una zona de falla y seguridad recibe un borrador verificado |
| 2:20 a 2:45 | Evaluación con IC, ablación `spark+sam`, Glimmer sin red |
| 2:45 a 3:00 | Cierre |

---

## 8. Muse Code: dónde usarlo de verdad

Hoy hay un archivo. La meta es que un juez vea Muse Code en **tres piezas reales** del trabajo nuevo, con la misma disciplina: tests escritos antes por nosotros, implementación de Muse Code sin editar, trazas limpias publicadas.

| Pieza | Por qué encaja | Spec | Dónde vive |
|---|---|---|---|
| Compuerta de entrada (A): la regla que combina las tres señales | Función pura con casos claros | Tests con confianzas y respuestas de Spark simuladas | `review.py` o un módulo nuevo `gate.py` |
| Constructor de prompts de SAM (B y C): pasar cajas y puntos a tokens `<|box;...|>` y `<|point;...|>`, validar `w` y `h`, máximo 16 | Puro, fácil de especificar, y muestra Muse Code trabajando sobre la API de Meta | Tests con los ejemplos de la doc | `meta_client.py` (la regla dice que las llamadas a Meta viven ahí; el constructor puede ser una función pura dentro del mismo archivo) |
| Agregación por profundidad del barreno (D): unir cajas, detectar huecos y traslapes, RQD por intervalo fijo | Es cálculo geotécnico, así que va en `geometry.py` con tests. Muse Code lo escribe contra tests nuestros, como hizo con `verify.py` | Tests con dos cajas de Onkalo y casos de borde | `geometry.py` |

Cómo dejar evidencia:
- Mismo método que `verify.py`: `muse exec --json`, trazas en `docs/muse-code/<pieza>-N.json`, sesión, número de llamadas, comando.
- En el commit, una línea `Implemented by Muse Code 1.4.13 (session ...)` y la lista en `APPLICATION.md` y en el README.
- Resolver o explicar el `"model": "muse-spark-1.3-contributor"` antes de publicar más trazas. Si el modo contributor estaba activo, solo pasó código del repo público, pero hay que decirlo así.
- No publicar `muse export --redacted`: trae reglas y skills personales de Raúl.
- Si la sandbox de Windows sigue sin arrancar PowerShell, correrlo en WSL o en el VPS para que Muse Code ejecute los tests él mismo. Eso hace la traza mucho más creíble.

Muse Code dentro del producto (idea para el video, no para el código): el geólogo pide una regla nueva en lenguaje natural ("avisa si el RQD baja de 25 en 3 m seguidos"), Muse Code escribe la verificación y sus tests en un sandbox, y una persona la aprueba antes de activarla. Es el patrón de BlinkFlow y encaja con Rule of Two. Construirlo ahora es riesgoso (ejecución de código en producción, sandbox de Windows rota); mostrarlo como siguiente paso es seguro.

---

## 9. Preguntas para #office-hours (Raúl decide si las publica)

- "Is there an open-weight SAM 3.1 checkpoint we can run locally, or only SAM 3 on Hugging Face?"
- "Our Muse Code trace reports `muse-spark-1.3-contributor` even with `--contributor-mode off`. Is that expected?"
- "For SAM 3.1 point prompts, is latency per request similar to text prompts?"
