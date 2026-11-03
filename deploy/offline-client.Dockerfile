FROM python:3.12-slim
RUN pip install --no-cache-dir "pydantic>=2.6" numpy opencv-python-headless httpx python-dotenv "meta-sam-parser>=0.1.0" fastapi python-multipart uvicorn
ENV PYTHONPATH=/app/src
WORKDIR /app
