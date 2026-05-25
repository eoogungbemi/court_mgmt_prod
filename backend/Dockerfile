FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system appgroup \
    && useradd  --system --gid appgroup --no-create-home appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R appuser:appgroup /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && gunicorn api.main:app \
     -w 4 -k uvicorn.workers.UvicornWorker \
     --bind 0.0.0.0:8000 \
     --access-logfile - \
     --error-logfile -"]
