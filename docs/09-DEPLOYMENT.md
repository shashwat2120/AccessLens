# 09 — Deployment

**Status:** v1.1 · **Last updated:** 2026-11-04

AccessLens ships as containers. `docker-compose.yml` runs the hardened API and UI as two containers on your own machine or server. For a free public demo on a host that runs one container with one public port, `deploy/container/` packages both as **one** container, and `render.yaml` describes it for Render (decisions: ADR-019, ADR-020).

## What the single container runs
- One container, uid 1000. `start.sh` generates a random API key at start-up, gives the API only its hash, starts the API on `127.0.0.1:8000` (not reachable from outside), then starts the Streamlit UI on `$PORT` (default 10000). The key is never printed or stored.
- `APP_ENV=prod`: the readability dictionary is baked into the image and nothing is downloaded at run time.
- Documents are processed in memory and never stored. Logs hold ids, sizes and counts, never document content.
- Measured locally under a 512 MB cap: about 246 MiB idle and 262 MiB after an audit, no out-of-memory kill.
- Rate limit: 60 requests a minute across all visitors (they share one internal key and address).

## Publish on Render (free)
You need a free Render account linked to your GitHub account. Check Render's current free-tier terms before relying on them; at the time of writing a free web service has 512 MB of memory and a small share of a CPU, sleeps after 15 minutes without traffic (about a minute to wake up), and has a monthly allowance of free hours.

1. Sign in at render.com with GitHub and allow it to read the `AccessLens` repository.
2. **New** → **Blueprint** → choose the repository. Render reads `render.yaml` and proposes one free web service, `accesslens`.
3. It asks for `GEMINI_API_KEY` and `GROQ_API_KEY`. Enter them to enable AI review, or leave them blank for rules-only checks. They are stored by Render, never in the repository.
4. **Deploy**. The first build takes several minutes. The app appears at the `onrender.com` address Render shows.

Updates are manual (`autoDeploy: false`): after merging to `main`, press **Manual Deploy** in Render.

## Verified deployment (2026-11-04)
Deployed from `main` at commit `9aae1ec` as a Blueprint on the free plan (Docker runtime, no payment method requested). Checked by hand on the live site:
- The sample deck returned score 52 ("Needs work") and 9 issues, identical to a local run, in about 5 seconds on the free CPU (about 1 second on a laptop).
- Requesting an API path (`/v1/rules`) on the public address returns the UI's HTML, not API data, so the API is not reachable from outside.
- After 15 minutes idle the service sleeps; the first request then shows Render's loading page for about a minute.
Not measured: the load target (p95 under 3 s for 10 concurrent audits) on this hardware, and large documents against the 45 s parse timeout.

## Settings you may change (Render → Environment)
| Variable | Effect |
|---|---|
| `LLM_ENABLED=false` | Turns AI review off for everyone (rules-only). Use this if the free AI quota is being used up. |
| `LLM_MODEL_PRIMARY`, `LLM_MODEL_FALLBACK` | Model names. Defaults are in the Dockerfile; check a model with a real call before changing it (ADR-016). |
| `LLM_REQUESTS_PER_MINUTE`, `LLM_BUDGET_PER_DOC` | Caps on AI usage (defaults 10 a minute, 10 calls a document). |
| `RATE_LIMIT` | Requests a minute across all visitors (default 60). |
| `PARSE_TIMEOUT_S`, `REQUEST_TIMEOUT_S` | Set to 45 and 80 in `render.yaml` because the free CPU is slow. |
| `ACCESSLENS_DISABLE_XSRF=true` | Only for a host that shows the app in an iframe on another origin (such as a Hugging Face Space), where uploads fail with XSRF protection on. |

## Things to know
- **Privacy.** The page tells visitors that AI review sends short text excerpts and images with alt text to Google Gemini (Groq as a fallback) and that free tiers may use them to improve products. A public demo should not be used for confidential documents.
- **Shared quota.** Anyone can switch AI review on and spend your free-tier quota. AI review is off by default and capped (above); turn it off with `LLM_ENABLED=false` if needed.
- **Speed.** On the free plan the first visit after a sleep takes about a minute, and audits are slower than on a laptop because of the small CPU share. Large documents may hit the timeouts.
- **No login.** The UI has no accounts. Anyone with the link can use it.
- **Not for sensitive production use.** It is a single instance with in-memory limits. For a real service, run the two-container setup behind your own proxy and add real authentication.
- **Hugging Face Spaces.** At the time of writing, Docker Spaces require a paid plan, so the free route here is Render. The same image works there if you pay: set `ACCESSLENS_DISABLE_XSRF=true`, `PORT=7860` and add a Space card (`sdk: docker`, `app_port: 7860`).
