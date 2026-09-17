FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY connector ./connector
RUN mkdir -p /app/data && useradd --create-home --uid 10001 connector \
    && chown -R connector:connector /app
USER connector

CMD ["python", "-m", "connector.main"]
