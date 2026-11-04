# 09 — Deployment

**Status:** v1.0 · **Last updated:** 2026-11-04

AccessLens ships as containers (see `docker-compose.yml` for two containers on your own machine or server). For a free public demo, `deploy/huggingface/` packages the API and the UI as **one** container for a Hugging Face Space (decision: ADR-019).

## What the Space runs
- One container, uid 1000, port 7860. `start.sh` generates a random API key at start-up, gives the API only its hash, starts the API on `127.0.0.1:8000` (not reachable from outside), then starts the Streamlit UI on port 7860. The key is never printed or stored.
- `APP_ENV=prod`: the readability dictionary is baked into the image and nothing is downloaded at run time.
- Documents are processed in memory and never stored. Logs hold ids, sizes and counts, never document content.
- Rate limit: 60 requests a minute across all visitors (they share one internal key and address), set in the Dockerfile.

## Publish it (one-off)
You need a free Hugging Face account. Your token is typed only into your own terminal; nobody else needs it.

1. On huggingface.co: **New Space** → name `accesslens` → SDK **Docker** (Blank) → **Public** → CPU basic (free) → Create.
2. Settings → Access Tokens → create a token with **Write** access. Keep it private.
3. In the Space: Settings → **Variables and secrets** → add secrets `GEMINI_API_KEY` and `GROQ_API_KEY` (optional). Without them the app still works with rules-only checks.
4. Build the folder and push it (replace `YOUR-NAME`):

```bash
uv run python deploy/huggingface/build_space.py build/space
cd build/space
git init -b main
git add .
git commit -m "Deploy AccessLens"
git remote add space https://huggingface.co/spaces/YOUR-NAME/accesslens
git push space main
```

When git asks, the username is your Hugging Face username and the password is the token. The Space builds the image (a few minutes) and then shows the app at `https://YOUR-NAME-accesslens.hf.space`.

To update later, run the build script again and push the new folder contents.

## Settings you may change (Space → Settings → Variables)
| Variable | Effect |
|---|---|
| `LLM_ENABLED=false` | Turns AI review off for everyone (rules-only). Use this if the free AI quota is being used up. |
| `LLM_MODEL_PRIMARY`, `LLM_MODEL_FALLBACK` | Model names. Defaults are in the Dockerfile; check a model with a real call before changing it (ADR-016). |
| `LLM_REQUESTS_PER_MINUTE`, `LLM_BUDGET_PER_DOC` | Caps on AI usage (defaults 10 a minute, 10 calls a document). |
| `RATE_LIMIT` | Requests a minute across all visitors (default 60). |

## Things to know
- **Privacy.** The page tells visitors that AI review sends short text excerpts and images with alt text to Google Gemini (Groq as a fallback) and that free tiers may use them to improve products. A public demo should not be used for confidential documents.
- **Shared quota.** Anyone can switch AI review on and spend your free-tier quota. AI review is off by default and capped (above); turn it off with `LLM_ENABLED=false` if needed.
- **No login.** The UI has no accounts. Free Spaces may sleep when idle and take a short while to wake; check Hugging Face's current documentation for hardware limits.
- **Iframe and XSRF.** A Space shows the app inside an iframe on another origin, where Streamlit's XSRF protection makes uploads fail, so `start.sh` turns it off. The app has no cookies, sessions or stored data for a forged request to reach.
- **Not for sensitive production use.** It is a single instance with in-memory limits. For a real service, run the two-container setup behind your own proxy and add real authentication.
