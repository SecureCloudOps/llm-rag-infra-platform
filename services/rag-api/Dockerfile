# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EMBEDDING_CACHE_DIR=/models \
    HF_HOME=/models/hf \
    OMP_NUM_THREADS=2
WORKDIR /app
RUN groupadd --gid 1000 app && useradd --uid 1000 --gid 1000 --no-create-home appuser \
    && mkdir /models && chown 1000:1000 /models
COPY requirements.lock ./
# Optional corporate proxy CA; the session certificate stays outside image layers.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install -r requirements.lock
COPY pyproject.toml README.md ./
COPY --chown=1000:1000 app ./app
RUN PIP_DISABLE_PIP_VERSION_CHECK=1 pip install --no-deps --no-build-isolation .
USER 1000:1000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=900s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3).read()"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
