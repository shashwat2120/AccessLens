#!/usr/bin/env bash
# Starts the API (internal) and the UI (public, on $PORT) in one container.
set -euo pipefail

# A one-off key shared only by the two processes in this container. It is never printed,
# written to disk or logged; only its hash is given to the API.
ACCESSLENS_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
API_KEYS_SHA256="$(printf %s "$ACCESSLENS_API_KEY" \
  | python -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')"
export ACCESSLENS_API_KEY API_KEYS_SHA256

uvicorn --factory accesslens.api.main:app_factory --host 127.0.0.1 --port 8000 --proxy-headers &

for _ in $(seq 1 90); do
  if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)" 2>/dev/null; then
    break
  fi
  sleep 1
done

# XSRF protection stays on (Streamlit's default). Only a host that shows the app inside an
# iframe on another origin needs it off; set ACCESSLENS_DISABLE_XSRF=true for such a host.
xsrf=true
if [ "${ACCESSLENS_DISABLE_XSRF:-false}" = "true" ]; then xsrf=false; fi

streamlit run ui/streamlit_app.py \
  --server.port="${PORT:-10000}" --server.address=0.0.0.0 \
  --server.enableXsrfProtection="$xsrf" --server.enableCORS=false &

# If either process stops, stop the container so the platform restarts it.
wait -n
exit 1
