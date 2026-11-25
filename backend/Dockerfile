FROM python:3.12.6-slim

WORKDIR /app

ENV UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ ./common/
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY openapi.yaml ./openapi.yaml

EXPOSE 8000
CMD ["uvicorn", "backend.main:app"]
