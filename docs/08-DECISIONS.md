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

## ADR-009 — Eval corpus is generated, not committed; python-docx is a dev dependency
**Date:** 2026-11-03 · **Status:** Accepted
**Context:** The corpus (30 synthetic, 5 clean, 5 injection .docx) must regenerate from one command, and the answer key must stay in step with it.
**Decision:** `eval/generate_corpus.py` builds the documents with python-docx (dev dependency until Phase 2) from a fixed seed. `eval/answer_key.csv` is committed; `eval/corpus/` is git-ignored. `block_order` is the 0-based index of a body-level paragraph or table. Documents with no heading styles also list HDG-005, since they cannot start with H1/Title. The "image containing written instructions" injection is approximated with a payload in the image title attribute.
**Consequences:** Reviewable answer-key diffs and no binaries in git. Document bytes are not identical across runs (zip timestamps), but content and key are. The key encodes expectations before any rule exists, so Phase 3 may show the key or a rule is wrong; fix whichever is wrong in the same change.

## ADR-010 — Ingest: stdin sandbox, in-memory validation, POSIX-only memory limit
**Date:** 2026-11-03 · **Status:** Accepted
**Context:** SECURITY §3-§4 require validation before parsing and a resource-limited child process. Development is on Windows, where `resource.setrlimit` does not exist.
**Decision:** `validate_docx` inspects the zip in memory and rejects any XML part containing a DOCTYPE, including UTF-16 or non-UTF-8 encoded parts that would hide it from a byte search. The per-entry compression-ratio check applies only to entries of 4 KiB or more, because tiny XML can legitimately compress past 100:1 and cannot exhaust memory. The sandbox passes the document to the child over stdin, so no work file or filename ever exists, and gives the child a minimal environment (no API keys). `python-docx` and `lxml` are runtime dependencies; `hypothesis` is a dev dependency. All limits are config (`MAX_ZIP_ENTRIES`, `MAX_UNCOMPRESSED_MB`, `MAX_COMPRESSION_RATIO`, `PARSE_TIMEOUT_S`, `PARSE_MEMORY_MB`).
**Consequences:** The 512 MB memory cap is enforced on Linux (the production target) only; on Windows only the wall-clock timeout applies, and a Windows Job Object would be needed to close that gap. The worker re-validates its input, so the sandbox does not trust its caller. Images and links inside table cells are attributed to the table's block.

## ADR-011 — Rule engine: hits become findings in one place; textstat for reading grade
**Date:** 2026-11-03 · **Status:** Accepted
**Context:** 23 rule-based checks need consistent ids, snippets and metadata, and one failing rule must not stop the rest.
**Decision:** A rule's check is a pure function `(ParsedDocument, RuleConfig) -> list[Hit]`; `Rule.run` builds the `Finding` objects (id, severity, WCAG, snippet capped at 120 characters with control characters stripped). Rules register under their catalog id with a decorator, and a test fails if the registry and the catalog disagree on ids or severities. Every threshold lives in `RuleConfig`. `textstat` (runtime dependency, pulls in nltk, pyphen and others) computes the Flesch-Kincaid grade per heading section, and only for sections of at least 30 words, because shorter text scores unreliably; list items and fragments are treated as sentences. A "fake list" needs at least 2 consecutive typed-marker paragraphs. HDG-003 reports confidence 0.8, as the catalog says. Findings sort by severity, WCAG level, rule frequency, then position; the score formula is TRD §6 with the 60 normalizer.
**Consequences:** Adding a rule is one decorated function plus a catalog row and fixtures. The first rules-only eval scored 100% recall and precision with no false positives on all 79 rule-based key rows. That is expected, because the same author wrote the generator and the rules; it proves the pipeline and the block-order convention, not real-world accuracy. The real-world documents (Phase 1) are what will test the heuristics, especially HDG-003, TXT-001 and CLR-001, which ignore formatting inherited from styles.

## ADR-012 — LLM layer: the item fixes the rule, the LLM only judges
**Date:** 2026-11-03 · **Status:** Accepted
**Context:** SECURITY §5 requires the LLM to be a tool-less classifier that can only add findings for IMG-003, LNK-003 and TXT-006 (plus rewrite suggestions), whatever the document says.
**Decision:** The pipeline, not the model, decides which rule an item belongs to; the model returns `issue`, `confidence`, `message` and `suggestion` per item, echoing the rule id, and any answer with an unknown item id, a different rule id, or a duplicate id is discarded. The output schema limits the rule id to the five allowed values, so anything else fails validation, is retried once and then dropped with a warning. Items are batched per rule (8 per call, 4 when images are attached) and sent inside `<document_item>` tags with `&`, `<` and `>` escaped. Every string is redacted (emails, phones, long digit runs), whitespace-collapsed and capped at 600 characters before it leaves the process; link destinations are reduced to scheme, host and path. Vision items go to a vision-capable provider; if only a text-only provider answers, the alt-text review runs without the image and its confidence drops by 0.2. Findings below `LLM_MIN_CONFIDENCE` (0.5) are suppressed. Transient errors (429, 5xx, timeouts) back off and retry, then fall back to the second provider; every attempt counts against the per-document call budget. The runner never raises: failures become a warning and `degraded=true`. Provider library retries are off so the budget is exact, and LangSmith tracing is forced off unless configured. `langchain-core`, `langchain-google-genai` and `langchain-groq` are runtime dependencies. Results are cached in memory only (key: prompt version, rule, model, content hash); there is no disk cache, so nothing derived from a document is written to disk.
**Consequences:** Injection cannot add a rule, remove a rule finding or alter anything but suggestion text (`apply_rewrites`). It can still make the model wrongly stay silent or flag an item, which is what the injection eval measures with a real model. Prompts, parsing and fallback are covered by tests with a fake model only; agreement, injection success and real latency are unmeasured until the keys are set up. Image bytes cannot be redacted, which the privacy notice must say. A document's first-use context for TXT-006 is approximated by paragraph, not by document order.

## ADR-013 — Pipeline: one LangGraph graph behind `AuditService`; all untrusted parsing stays sandboxed
**Date:** 2026-11-03 · **Status:** Accepted
**Context:** Phase 5 wires validation, parsing, rules, the LLM layer and reporting into the single entry point every interface will call (TRD §1, §4).
**Decision:** `AuditService.audit(bytes, AuditOptions) -> Report` runs a LangGraph `StateGraph`: `validate -> parse -> rule_checks -> (select_llm_items -> llm_checks | skip) -> merge -> build_report`. The conditional edge skips the LLM nodes in rules-only mode. Node names differ from state keys because LangGraph forbids sharing one, so the TRD's `report` node is `build_report`. Validation runs in-process so typed errors (`macro_enabled`, `file_too_large`, ...) reach the caller; parsing and, new in this phase, image extraction both run in the subprocess sandbox, so no untrusted document is ever parsed in the main process (extraction is a second subprocess call, only when the document has images). If the server has the LLM disabled, a "full" request becomes rules-only with a warning. A full-mode report always carries LLM usage, with zero calls when nothing needed review. Merging is additive: rule findings pass through untouched except rewrite suggestions, exact duplicates (rule, block, message) collapse to the most confident copy, and the result is priority-sorted. Each audit gets a request id and logs one JSON `audit_done` event (request id, file sha256, size, mode, per-node milliseconds, findings by severity, score, LLM calls and tokens, degraded flag) and no document content; `logging.configure_logging` renders structlog and stdlib logs as one JSON object per line. `langgraph` and `structlog` are runtime dependencies.
**Consequences:** Interfaces stay thin and cannot bypass validation or the sandbox. Tests inject in-process parsing for speed and use the real sandbox for one document to prove both paths give the same report. The first audit in a fresh process takes several seconds, mostly `textstat` loading its dictionary on first use; warm it at startup and re-check rules-only latency against the p95 target in the Phase 7 load test. The injection and LLM-agreement evals still need real keys (ADR-012).
