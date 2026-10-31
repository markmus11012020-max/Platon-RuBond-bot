FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Moscow

WORKDIR /app

COPY bondbot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY bondbot ./bondbot

RUN useradd --create-home --uid 10001 bondbot \
    && mkdir -p /data \
    && chown -R bondbot:bondbot /app /data

USER bondbot

EXPOSE 8081

CMD ["python", "-m", "bondbot.main"]
