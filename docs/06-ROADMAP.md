# 06 — Roadmap & Build Checklist

**Status:** Living document — tick boxes as you go. **Start:** 2026-11-03
Estimated ~5 weeks at a few hours a day. Each phase ends with a **Definition of Done (DoD)**; don't start the next phase until the DoD is met.

Current phase: **Phase 7** (Phases 0-6 complete except the open items: branch protection and API keys in Phase 0, real-world documents in Phase 1, and the real-model injection and agreement evals in Phase 4)

---

## Phase 0 — Project setup (Days 1–2)
- [ ] Create GitHub repo `accesslens` (public), add MIT LICENSE
- [ ] Copy `docs/`, `CLAUDE.md`, `README.md` into the repo
- [ ] `uv init`, Python 3.12, `src/` layout per TRD §9
- [ ] Add ruff, mypy, pytest, pre-commit (ruff, mypy, gitleaks, bandit)
- [x] `.gitignore`, `.env.example`, `config.py` with pydantic-settings
- [ ] CI workflow: lint, type-check, test, pip-audit, gitleaks
- [ ] Branch protection on `main`
- [ ] Get Gemini API key (Google AI Studio) and Groq key; store in `.env` only; record model names + free limits in `08-DECISIONS.md`

**DoD:** empty package installs, `pytest` runs, CI green on first PR.

## Phase 1 — Eval corpus & answer key (Days 3–5)
- [x] `eval/generate_corpus.py` — 30 synthetic docs with planted issues covering every rule
- [x] 5 clean control docs, 5 injection docs
- [x] `answer_key.csv` generated alongside the corpus
- [ ] Collect 5–10 openly licensed real docs, label by hand, record sources

**DoD:** corpus regenerates from one command; every rule ID has ≥ 3 planted instances.

## Phase 2 — Secure ingest & parser (Days 6–10)
- [x] `models.py` (TRD §3)
- [x] `ingest/validate.py` — all checks in SECURITY §3
- [x] `ingest/sandbox.py` — subprocess, timeout, memory limit (memory limit POSIX only; see ADR-010)
- [x] `ingest/parse_docx.py` — blocks, headings, runs, images (alt, decorative, inline/anchor), tables, links, meta
- [x] Security fixtures + tests (zip bomb, XXE, billion laughs, docm, zip-slip, oversize, external links)
- [x] Hypothesis fuzz test for parser

**DoD:** every corpus doc parses to valid `ParsedDocument`; `tests/security` green.

## Phase 3 — Rule engine (Days 11–15)
- [x] `rules/base.py` registry + `Finding` builder
- [x] Implement all rule-based checks in `04-RULES-CATALOG.md`
- [x] Unit tests: pass + fail fixture per rule
- [x] `report/prioritize.py`, `report/score.py`
- [x] `eval/run_eval.py` (rules-only) wired into CI

**DoD:** rule recall ≥ 98%, precision ≥ 95% on corpus; CI enforces it.

## Phase 4 — LLM checks (Days 16–20)
- [x] `llm/provider.py` (Gemini primary, Groq fallback, config-driven)
- [x] `llm/redact.py` (PII redaction) + tests
- [x] Prompts v1 for IMG-003 (vision), TXT-001/002 rewrites, LNK-003, TXT-006
- [x] Batching, structured output, schema validation, allowed-rule enforcement
- [x] Retry/backoff, fallback, degraded mode, budget, cache
- [ ] Injection eval passes (0 successes) — `make eval-llm` is written and tested with a fake model; needs real keys
- [ ] LLM eval run; record agreement % — needs real keys and model names in `.env`

**DoD:** LLM agreement ≥ 80%; injection 0; an LLM outage still returns a rules-only report with a warning.

## Phase 5 — LangGraph pipeline & service (Days 21–23)
- [x] `agent/state.py`, `nodes.py`, `graph.py` with rules-only conditional edge
- [x] `service.py` — `AuditService.audit()` single entry point
- [x] Integration tests over the corpus
- [x] Structured logging (no content) + per-node timings

**DoD:** `AuditService` produces full reports for the whole corpus in both modes.

## Phase 6 — Interfaces (Days 24–28)
- [x] CLI with exit codes
- [x] FastAPI: routes, API key auth, rate limits, size limits, problem+json errors, security headers, CORS
- [x] HTML report (autoescape, CSP) and XLSX export (formula-injection safe)
- [ ] MCP server: `audit_docx`, `list_rules`, `explain_rule`; path allowlist; tested with Claude Desktop/Claude Code — built and covered by automated tests; still to try by hand in Claude Desktop or Claude Code
- [x] Streamlit UI: privacy notice, rules-only toggle, upload, report view, downloads

**DoD:** all four interfaces audit the same file and return identical findings.

## Phase 7 — Production hardening & deploy (Days 29–33)
- [ ] Dockerfile (multi-stage, non-root, pinned base, read-only FS)
- [ ] Trivy scan in CI
- [ ] Deploy API + UI (Hugging Face Spaces or Render), HTTPS, prod config
- [ ] Complete SECURITY §11 checklist
- [ ] Load test: 10 concurrent rules-only audits
- [ ] Repo-root `SECURITY.md`, `CHANGELOG.md`

**DoD:** public demo live; security checklist fully ticked.

## Phase 8 — Portfolio polish (Days 34–36)
- [ ] README: problem, demo GIF, architecture diagram, results table, privacy note, how to run, limitations
- [ ] Final eval run published in `eval/results/`
- [ ] Short write-up / LinkedIn post: design decisions and what you learned
- [ ] Tag `v1.0.0`

**DoD:** someone new can understand, run, and trust the project in 5 minutes.

---

## Later (v2 ideas — not now)
- PDF support · PowerPoint support · auto-fix mode that writes a corrected .docx · checking against a course standard (curriculum gap idea) · Hindi/Indian-language readability · GitHub Action for docs repos.
