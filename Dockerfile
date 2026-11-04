# syntax=docker/dockerfile:1
#
# Targets: `api` (default, last stage) and `ui`. Both run as a non-root user and are meant to
# run with a read-only root filesystem and a tmpfs on /tmp (see docker-compose.yml).
#
# The base image is pinned by digest (SECURITY §10). Update it deliberately:
#   docker pull python:3.12-slim && docker inspect python:3.12-slim --format '{{index .RepoDigests 0}}'
ARG PYTHON_IMAGE=python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30

# ---- build stages: have the package manager and build tooling; none of it ships ---------
FROM ${PYTHON_IMAGE} AS builder-base
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv==0.13.7
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src

# Locked, production dependencies only, installed as a wheel (not editable) into /app/.venv.
# The API image leaves out the `ui` extra: Streamlit drags in pandas, numpy and pyarrow.
#
# The readability dictionary (NLTK cmudict) is fetched here, at build time, into /opt/nltk_data.
# The running service never downloads anything: APP_ENV=prod refuses to start without it.
FROM builder-base AS builder-api
RUN uv sync --frozen --no-dev --no-editable \
    && /app/.venv/bin/python -m nltk.downloader -d /opt/nltk_data cmudict

FROM builder-base AS builder-ui
RUN uv sync --frozen --no-dev --no-editable --extra ui \
    && /app/.venv/bin/python -m nltk.downloader -d /opt/nltk_data cmudict

# ---- runtime base: a non-root user and no build tools -----------------------------------
FROM ${PYTHON_IMAGE} AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    NLTK_DATA=/opt/nltk_data \
    APP_ENV=prod
RUN python -m pip uninstall -y pip setuptools wheel >/dev/null 2>&1 || true \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app

# ---- ui: Streamlit front end (a client of the API) --------------------------------------
FROM runtime AS ui
COPY --from=builder-ui --chown=app:app /app/.venv /app/.venv
COPY --from=builder-ui /opt/nltk_data /opt/nltk_data
COPY --chown=app:app ui ./ui
COPY --chown=app:app .streamlit ./.streamlit
USER 10001:10001
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ENABLE_CORS=false
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4).status == 200 else 1)"
CMD ["streamlit", "run", "ui/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]

# ---- api: the default target ------------------------------------------------------------
FROM runtime AS api
COPY --from=builder-api --chown=app:app /app/.venv /app/.venv
COPY --from=builder-api /opt/nltk_data /opt/nltk_data
USER 10001:10001
# Behind a reverse proxy set FORWARDED_ALLOW_IPS to the proxy's address so rate limits see the
# real client IP; the default trusts nobody but localhost.
ENV FORWARDED_ALLOW_IPS=127.0.0.1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "--factory", "accesslens.api.main:app_factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
