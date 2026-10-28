# CoreSight review API and page. Built on a workstation and loaded on the VPS
# (docs/DEPLOY.md). Only public sample photos go in the image: never the Kaggle set (NC).
FROM python:3.12-slim
# the VPS nightly prune keeps images with this label (docs/DEPLOY.md)
LABEL vps.keep=true

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
# editable: the app finds data/ next to src/, as in development
RUN pip install --no-cache-dir -e . && useradd --system --uid 10001 coresight

COPY data/labels/ONK-DTPH5.1_box05.json data/labels/ONK-DTPH5.1_box06.json data/labels/U12G-GF-GT2_box01.json data/labels/U12G-GF-GT2_box03.json ./data/labels/
COPY data/labels/pieces/ONK-DTPH5.1_box05.json data/labels/pieces/ONK-DTPH5.1_box06.json data/labels/pieces/U12G-GF-GT2_box01.json data/labels/pieces/U12G-GF-GT2_box03.json ./data/labels/pieces/
COPY data/raw/commons_onkalo_1.jpg data/raw/commons_nts_u12g_1.jpg data/raw/commons_nts_u12g_2.jpg ./data/raw/
COPY data/prices_example.json ./data/

RUN mkdir -p /app/data/reviews /app/data/cache && chown -R coresight /app/data
USER coresight
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "coresight.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
