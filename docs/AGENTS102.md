# Agents 102: agentes verificables (28 oct)

Fuente: la grabación del taller (Vimeo, unos 30 min), leída con sus subtítulos automáticos.
Imparte: Yash Khare, partner engineer de Meta (modelos abiertos y evals). Modera: Maya.
Ejemplo del taller: el agente legal del día anterior (checklist y memo), construido con Muse Code a partir de un repo y un handbook.

## Lo que enseñó

1. **La verificación no es una herramienta que el agente elige.** Si `verify` es una herramienta más, a veces la llama y a veces no. Va dentro de la herramienta de entrega (`submit_memo`): el agente no puede saltarla ni cambiarla. Puede haber checks extra opcionales, pero los obligatorios son parte del sistema.
2. **Dos capas.** Primero checks deterministas (formato, completitud, JSON válido, "no hay números si no debe haberlos"). Después LLM como juez para la corrección de cada afirmación. Hay que balancear las dos.
3. **Verificar en los hitos, no al final ni en todos lados.** En el taller se verifica el checklist antes del memo y el memo antes de entregar. Verificar todo agrega latencia; no verificar nada deja pasar errores.
4. **Comparar contra una verdad de referencia hecha por un experto.** El checklist del agente se compara con uno de un abogado y se acepta con 80 % de cobertura. El umbral lo fija el experto del dominio: en finanzas o salud, cerca de 100 %.
5. **Ciclo con retroalimentación.** Si falla, el resultado de la verificación regresa al agente y lo intenta de nuevo. En el taller la cobertura subió de 50 % a 67 % y a 83 % en tres intentos. Máximo 3 intentos; después se escala a una persona.
6. **Firma final de una persona.** Aunque pase todo, el memo espera la firma del abogado antes de salir.
7. **Lista cerrada de herramientas.** Si el agente pide una herramienta que no está en la lista, se descarta. Así se evita que cambie un documento después de aprobado.
8. **Velocidad contra precisión, medida.** Sin verificación el agente terminó en 20 turnos; con verificación, en 30. Lo enseñan como un costo que se acepta y se muestra.
9. **Feedback en hitos intermedios** cuando el resultado real tarda días en conocerse.
10. **Muse Code como constructor y como revisor.** Recomendó dos sesiones: una que solo escribe código y otra que solo revisa, sin poder cambiar nada. En el taller Muse Code escribió `verify_memo` y `verify_checklist`, falló y se corrigió pegándole el error.

## Cómo estamos en CoreSight

| Práctica | Hoy | Falta |
|---|---|---|
| Verificación obligatoria dentro de la entrega | Sí: `verify.py` corre siempre sobre cada borrador, no es una herramienta opcional | Decirlo así en el README y en el video, con esta misma frase |
| Checks deterministas | Sí: intervalos, cifras iguales a `geometry.py`, cada número trazable a una herramienta, precios de la tabla | |
| LLM como juez | No | Un juez (Muse Spark) que revise que cada afirmación de texto del borrador esté respaldada por la descripción aprobada del geólogo. Por ejemplo, "sulfuros visibles" solo si la descripción lo dice |
| Verificar en los hitos | Solo el borrador final | Verificar también la decisión del orquestador: que las áreas que eligió Wonder sean coherentes con los disparadores (RQD, sulfuros, cambio de litología) antes de redactar |
| Referencia de experto con umbral | La evaluación contra el geólogo de la mina (MAE 11.2) | Mostrar el umbral como decisión del geólogo, no nuestra |
| Ciclo con retroalimentación | Un reintento con los checks fallidos | Hasta 3 intentos y escalar a la persona con el motivo visible ("necesita revisión: 3 intentos fallidos") |
| Firma final humana | Sí: cada borrador tiene su botón de aprobar y nada se envía solo | |
| Lista cerrada de herramientas | Sí: herramientas de solo lectura y `unknown tool` se rechaza | Mencionarlo en el README |
| Costo de verificar, visible | No | Mostrar en el registro de decisiones turnos, intentos y segundos con y sin verificación |
| Muse Code constructor y revisor | Solo constructor | Una segunda sesión de Muse Code solo de revisión (sin escritura) sobre cada pieza que escribe, con su traza en `docs/muse-code/` |

## Cambios propuestos

Para E (agente de barreno, 31 oct), que ya toca `agents.py`:

1. Verificación del ruteo del orquestador como hito, antes de que redacten los agentes.
2. LLM como juez después de `verify.py`: Spark revisa cada afirmación de texto contra la descripción aprobada. Salida validada con Pydantic. El juez no puede aprobar algo que `verify.py` rechazó.
3. Hasta 3 intentos con la retroalimentación y escalar a la persona con el motivo.
4. Turnos, intentos y tiempo de verificación en el registro de decisiones.

Para la evidencia de Muse Code, desde D en adelante:

5. Cada pieza que escriba Muse Code pasa por una segunda sesión de Muse Code que solo revisa. Las dos trazas se publican.

Para el video y el README:

6. Usar el vocabulario del taller, porque es el de los jueces de Meta: "mandatory verification inside the submit step", "deterministic checks plus LLM as a judge", "verify at milestones", "max three attempts, then escalate to a human", "final human sign-off", "closed tool list".

## Velocidad sin quitar verificaciones (30 oct, punto 3 del tercer análisis)

El taller enseña que verificar cuesta y que el costo se muestra. En la caja del recorrido (Nevada U12G caja 3) los agentes tardaban 191 s, uno detrás de otro. Ningún check se quitó; cambió el orden y lo que se repetía:

- El ruteo empieza sobre un hallazgo que `verify.py` ya aprobó, mientras el juez lo lee. Solo se queda si el juez también lo aprueba; si no, se descarta y el registro lo dice.
- Laboratorio, seguridad y planta redactan y se juzgan a la vez. Finanzas espera la solicitud de laboratorio verificada.
- Un reintento sigue la misma conversación con solo las razones: el agente no vuelve a leer sus herramientas.
- Cada agente recibe en su primer mensaje lo que devuelven sus herramientas sin argumentos (resumen de la caja, tendencias, hallazgo, historial). La lista de herramientas es la misma y el registro dice qué recibió.
- Prompt caching de Meta (https://dev.meta.ai/docs/prompt-caching): es automático, sin parámetro. Lo probamos con la API real: el segundo llamado con el mismo prefijo reusó 1507 de 1551 tokens (`usage.input_tokens_details.cached_tokens`). El tiempo no estaba en la entrada sino en los turnos y la salida, así que no construimos nada encima.
- La página dice el paso y cuánto falta ("Step 2 of 3: the orchestrator is routing the box, about 1 min left").

| | Agente de barreno y juez | Ruteo | Borrador de seguridad y juez | Total |
|---|---|---|---|---|
| Antes (una corrida; el juez regresó una vez el hallazgo y una vez el borrador) | 75 s | 18 s | 99 s | 191 s |
| Después, local (tres corridas seguidas) | 26 a 46 s | 0 a 2 s después del hallazgo | 44 a 54 s | 73, 90 y 96 s |

Punto 7, en el mismo espíritu ("la firma final es de una persona"): las acciones que propone un borrador salen de una lista cerrada (`schemas.DraftAction`) y `verify.check_role` rechaza cualquier texto que pare la operación ("Do not continue drilling until..."). El juez también lo revisa: proponer una revisión o un aviso es su trabajo; ordenar que se pare, no.
