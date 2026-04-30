FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PAPERLITE_DB_PATH=/data/paperlite.sqlite3 \
    PAPERLITE_HEALTH_SNAPSHOT_PATH=/data/endpoint_health_snapshot.json

WORKDIR /app

COPY paperlite/ ./paperlite/
COPY main.py README.md PAPERLITE_CURRENT_STATE.md SOURCES.md DEPLOYMENT.md ./

RUN pip install --no-cache-dir -e ./paperlite

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
