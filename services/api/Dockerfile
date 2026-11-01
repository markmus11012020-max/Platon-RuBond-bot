FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    TZ=Europe/Moscow

WORKDIR /app

COPY bondbot/certs/russian_trusted_root_ca.crt /usr/local/share/ca-certificates/russian_trusted_root_ca.crt
COPY bondbot/certs/russian_trusted_sub_ca.crt /usr/local/share/ca-certificates/russian_trusted_sub_ca.crt
RUN update-ca-certificates

COPY services/api/requirements.txt ./services/api/requirements.txt
RUN pip install --no-cache-dir -r services/api/requirements.txt

COPY bondbot ./bondbot
COPY services/api ./services/api

WORKDIR /app/services/api

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
