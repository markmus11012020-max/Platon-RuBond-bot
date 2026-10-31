FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Moscow

WORKDIR /app

COPY bondbot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# T-Invest API uses the Russian Trusted Root/Sub CA chain.
# Debian slim does not trust it, so add the official certificates.
COPY bondbot/certs/russian_trusted_root_ca.crt /usr/local/share/ca-certificates/russian_trusted_root_ca.crt
COPY bondbot/certs/russian_trusted_sub_ca.crt /usr/local/share/ca-certificates/russian_trusted_sub_ca.crt
RUN update-ca-certificates

COPY bondbot ./bondbot

RUN useradd --create-home --uid 10001 bondbot \
    && mkdir -p /data \
    && chown -R bondbot:bondbot /app /data

USER bondbot

EXPOSE 8081

CMD ["python", "-m", "bondbot.main"]
