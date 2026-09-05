# Self-contained build from a clean Git clone. No committed WASM is required.
# Override PYTHON_IMAGE with a reviewed digest in a reproducible deployment.
ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE} AS webbuild
RUN apt-get update && apt-get install -y --no-install-recommends clang lld \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY core/ core/
COPY ui/ ui/
COPY platform/ platform/
COPY tools/ tools/
COPY web/ web/
COPY docs/THIRD_PARTY.md docs/THIRD_PARTY.md
COPY LICENSE LICENSE
RUN bash tools/build-preview.sh

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PAPERWEEK_SITE_DIR=/app/site PAPERWEEK_DATA_DIR=/data
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && groupadd --gid 10001 paperweek \
    && useradd --uid 10001 --gid 10001 --no-create-home paperweek \
    && mkdir /data && chown 10001:10001 /data
COPY backend/ /app/backend/
COPY --from=webbuild /src/dist-preview/ /app/site/
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)" || exit 1
# Exactly ONE worker: one in-process scheduler, limiter and refresh lock.
CMD ["uvicorn", "backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
