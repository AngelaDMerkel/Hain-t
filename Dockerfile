FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    DATABASE_PATH=/data/dro.sqlite3

WORKDIR /opt/dro

RUN useradd --create-home --uid 10001 dro \
    && mkdir -p /data \
    && chown dro:dro /data

COPY app/ ./app/

USER dro

EXPOSE 8080

VOLUME ["/data"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=3s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2)"]

CMD ["python", "-m", "app.server"]
