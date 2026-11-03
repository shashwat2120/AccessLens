# 08 — Decision Log (ADRs)

Short records of important choices: context, decision, consequences. Add new entries at the bottom; never edit old ones — supersede them.

---

## ADR-001 — Word (.docx) only for v1
**Date:** 2026-11-03 · **Status:** Accepted
**Context:** PowerPoint and PDF were considered. PDF parsing (tagged vs untagged, reading order) adds major complexity.
**Decision:** Support .docx only. Design the parser output (`ParsedDocument`) to be format-neutral so other formats can be added later.
**Consequences:** Tighter scope, higher quality. PDF/PPTX listed as v2.

## ADR-002 — LangGraph over CrewAI
**Date:** 2026-11-03 · **Status:** Accepted
**Context:** The workflow is a fixed pipeline with one conditional branch, not open-ended multi-agent collaboration.
**Decision:** LangGraph `StateGraph` with plain-function nodes.
**Consequences:** Predictable, testable, traceable; less "agentic" marketing, but easier to defend in interviews ("why not multiple agents?" → no task needs negotiation between agents; a deterministic graph is cheaper and more reliable).

## ADR-003 — Free-tier LLMs: Gemini primary, Groq fallback, provider-swappable
**Date:** 2026-11-03 · **Status:** Accepted
**Context:** Must run at $0. Need vision for alt-text checks, structured JSON output, and enough daily quota.
**Decision:**
- **Primary: Google Gemini (Flash / Flash-Lite family) via Google AI Studio free tier** — vision-capable, large context, reliable structured output.
- **Fallback: Groq free tier** — fast, OpenAI-compatible, no credit card; used for text checks when Gemini is rate-limited or down.
- Provider and model names are config, behind `llm/provider.py`.
**Consequences:**
- Free-tier limits are low and change over time; actual limits are shown in AI Studio / Groq console. Record what you see here when you set up: model names, RPM, RPD, TPM, date checked.
- Gemini's free tier may use prompts to improve Google's products → privacy notice + rules-only mode + PII redaction (SECURITY §6).
- Batching and caching are required to stay inside daily request limits.

| Provider | Model | RPM | RPD | TPM | Checked on |
|---|---|---|---|---|---|
| Gemini | _fill in_ | | | | |
| Groq | _fill in_ | | | | |

## ADR-004 — Rules first, LLM only for judgment calls
**Date:** 2026-11-03 · **Status:** Accepted
**Decision:** Deterministic rules for anything objectively checkable; LLM only for IMG-003, LNK-003, TXT-006 and rewrite suggestions. LLM may add findings but never remove rule findings.
**Consequences:** Accurate, cheap, explainable; resistant to prompt injection; works fully offline in rules-only mode.

## ADR-005 — FastAPI backend, Streamlit UI as a thin client
**Date:** 2026-11-03 · **Status:** Accepted
**Decision:** All logic in a FastAPI service; Streamlit calls the API with a server-side key.
**Consequences:** One security boundary to harden; the UI can be replaced later without touching logic.

## ADR-006 — No persistent storage
**Date:** 2026-11-03 · **Status:** Accepted
**Decision:** Process in memory/temp and discard; no database, no saved reports.
**Consequences:** Strong privacy story, simpler ops. No history feature in v1.

## ADR-007 — MCP over stdio only
**Date:** 2026-11-03 · **Status:** Accepted
**Decision:** Local stdio MCP server with a path allowlist; no remote HTTP MCP in v1.
**Consequences:** No network attack surface for MCP; remote MCP would need auth (OAuth) and is deferred.

## ADR-008 — uv for dependency management
**Date:** 2026-11-03 · **Status:** Accepted
**Decision:** uv with a committed lockfile.
**Consequences:** Fast, reproducible installs in CI and Docker.
