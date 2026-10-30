FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Moscow

WORKDIR /app

COPY bondbot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY bondbot ./bondbot

RUN mkdir -p /data
EXPOSE 8081

CMD ["python", "-m", "bondbot.main"]
