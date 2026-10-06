# InsightDesk backend image.
# Build context: ./backend (see docker-compose.yml). The image mirrors the repo
# layout (/app/backend/app/...), so PROJECT_ROOT resolves to /app and relative
# paths such as ./data/insightdesk.db land in the mounted /app/data volume.

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PROJECT_ROOT=/app \
    HF_HOME=/app/data/.cache/huggingface

WORKDIR /app/backend

# CPU-only torch keeps the image ~2 GB smaller than the default CUDA build;
# embeddings for a prototype knowledge base do not need a GPU.
COPY requirements.txt .
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 10001 insightdesk \
    && mkdir -p /app/data \
    && chown -R insightdesk:insightdesk /app
USER insightdesk

EXPOSE 8000

# Liveness only: /health also probes Ollama, which may legitimately be down.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4).status == 200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host ${API_HOST:-0.0.0.0} --port ${API_PORT:-8000} --no-access-log"]
