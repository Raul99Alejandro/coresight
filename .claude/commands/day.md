---
description: Qué toca hoy en el plan del hackathon y las 3 primeras tareas
---

1. Lee `docs/PLAN.md` y `CLAUDE.md`.
2. Calcula la fecha de hoy en America/Mexico_City (por ejemplo `python -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo('America/Mexico_City')))"`; en Windows puede requerir `pip install tzdata`) y di qué día del plan es (0 a 11; el plan puede ir adelantado respecto a la fecha), su objetivo y su criterio "listo cuando". Di cuántas horas faltan para la entrega (mié 4 nov 2026, 20:00 hora de Zacatecas).
3. Revisa `git log --oneline -15` y `git status`.
4. Corre `.venv\Scripts\python -m pytest -q` y reporta el resultado.
5. Compara lo hecho contra el plan: qué días quedaron atrasados o adelantados.
6. Propón las 3 primeras tareas de hoy, en orden, cada una con su criterio de terminado.

No escribas ni modifiques código hasta que Raúl confirme.
