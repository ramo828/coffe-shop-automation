# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --upgrade pip && /opt/venv/bin/pip install -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    COFFEE_ENV=production
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY app ./app
COPY run.py seed.py pyproject.toml README.md ./
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin coffee \
    && mkdir -p /app/data \
    && chown -R coffee:coffee /app
USER coffee
EXPOSE 8000
VOLUME ["/app/data"]
CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8000"]
