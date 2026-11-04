# syntax=docker/dockerfile:1
#
# Single-container image for hosts that run one container and expose one port (Render, and
# similar). Build from the repository root:
#   docker build -f deploy/container/Dockerfile -t accesslens-single .
# The API listens on 127.0.0.1 only; the Streamlit UI listens on $PORT (default 10000) and is the
# only public surface. For two containers on your own machine use the main Dockerfile and
# docker-compose.yml instead.
#
# The base image is pinned by digest, as in the main Dockerfile (SECURITY §10).
ARG PYTHON_IMAGE=python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30

FROM ${PYTHON_IMAGE} AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv==0.13.7
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
# Locked production dependencies plus the UI extra. The readability dictionary is fetched here,
# at build time: the running service never downloads anything (APP_ENV=prod enforces it).
RUN uv sync --frozen --no-dev --no-editable --extra ui \
    && /app/.venv/bin/python -m nltk.downloader -d /opt/nltk_data cmudict

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    NLTK_DATA=/opt/nltk_data \
    APP_ENV=prod \
    PORT=10000 \
    FORWARDED_ALLOW_IPS=127.0.0.1 \
    ACCESSLENS_API_URL=http://127.0.0.1:8000 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    RATE_LIMIT=60/minute \
    LLM_MODEL_PRIMARY=gemini-3.5-flash-lite \
    LLM_MODEL_FALLBACK=openai/gpt-oss-120b
RUN python -m pip uninstall -y pip setuptools wheel >/dev/null 2>&1 || true \
    && useradd --system --uid 1000 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder /opt/nltk_data /opt/nltk_data
COPY --chown=app:app ui ./ui
COPY --chown=app:app .streamlit ./.streamlit
COPY --chown=app:app deploy/container/start.sh ./start.sh
USER 1000:1000
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/_stcore/health' % os.environ['PORT'], timeout=4).status == 200 else 1)"
CMD ["bash", "/app/start.sh"]
