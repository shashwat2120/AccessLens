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
| Gemini | `gemini-3.5-flash-lite` (vision, structured output verified with a real call) | not recorded | not recorded | not recorded | 2026-11-04 |
| Groq | `openai/gpt-oss-120b` (text only, structured output verified with a real call) | not recorded | not recorded | not recorded | 2026-11-04 |

Free-tier limits were not recorded: read them in AI Studio (https://aistudio.google.com/rate-limit) and the Groq console, then fill the table in. The default `LLM_REQUESTS_PER_MINUTE=10` is a conservative guess, not a measured limit. Lessons from the first real calls are in ADR-016.

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

## ADR-014 — Interfaces: one service behind four thin front ends; rate limiting with `limits`, not slowapi
**Date:** 2026-11-03 · **Status:** Accepted
**Context:** Phase 6 adds the CLI, REST API, MCP server and Streamlit UI. Each must call only `AuditService` and return identical findings.
**Decision:**
- **Rate limiting:** a first slowapi version let failed logins through unthrottled, because slowapi skips routes that carry their own limit and its decorator runs only after the auth dependency succeeds. It is replaced by the `limits` library (slowapi's engine) used as FastAPI dependencies: a per-IP check on every `/v1` route that runs before authentication, and a per-API-key check after it. `/healthz` and `/readyz` are exempt. Storage is in memory, which fits a stateless service. Behind a proxy, uvicorn needs `--proxy-headers` and a trusted `--forwarded-allow-ips`, or every caller shares the proxy's IP (Phase 7). This supersedes the slowapi line in TRD §2.
- **API:** keys are SHA-256 hashes compared in constant time; with no keys configured every request is refused. Bodies are capped as bytes arrive (413 before parsing), uploads are read with a hard cap and the file name is never used or echoed. Errors are RFC 9457 problem+json with `urn:accesslens:problem:<code>` types and generic text. Security headers go on every response, including errors; the HTML report adds the strict CSP. CORS has no wildcard and refuses `*` in production; `/docs` and `/openapi.json` are off in production. Slow requests return 504.
- **Reports:** HTML is autoescaped with no scripts. XLSX cells that start with `=`, `+`, `-`, `@`, tab or CR get a leading apostrophe and are stored as strings.
- **MCP:** official `mcp` SDK (2.x, `MCPServer`), stdio only. Paths are resolved with `realpath` and must lie inside `MCP_ALLOWED_DIR`; with no folder set, no file can be read. Output is capped at the top 25 findings with 120-character snippets.
- **UI:** a pure API client holding the key server-side. Each check makes three API calls (JSON, HTML, XLSX) so the download buttons have their data; the in-memory LLM cache stops that tripling AI calls, but it does count three requests against the rate limit. Rules only is the default.
- **CLI:** exit 0 when nothing critical or high, 1 when something is, 2 on any error; folders and xlsx need `--out`.
- A test runs the same file through the CLI, API, UI client and MCP tool and requires identical findings and score.
**Consequences:** The symlink-escape test for the MCP path guard is skipped on this Windows machine (creating symlinks needs elevated rights); the guard itself is `realpath`-based and the traversal, absolute-path and name-prefix cases are tested. The MCP server has been tested in-process only, not yet by hand in Claude Desktop or Claude Code. The UI's triple request could be replaced by on-demand downloads later.

## ADR-015 — Container hardening, no runtime downloads, and a cheaper sandbox child
**Date:** 2026-11-04 · **Status:** Accepted
**Context:** Phase 7 packages the service. Building and running it on Linux, and running the test suite inside a Linux container, surfaced three things that tests on Windows could not.
**Decision:**
- **Images:** a multi-stage Dockerfile pins `python:3.12-slim` by digest, installs locked production dependencies as a wheel, and ships neither pip, uv nor compilers. Both targets run as uid 10001, are meant to run read-only with a tmpfs `/tmp`, all capabilities dropped and `no-new-privileges` (`docker-compose.yml`). The `api` target omits the `ui` extra, since Streamlit pulls in pandas, numpy and pyarrow (the API image is about 430 MB; the UI image about 1 GB). CI builds both images on every PR, smoke-tests the hardened API image (health, readiness, non-root) and runs Trivy (CRITICAL and HIGH with a fix) on pushes to main and tags. Dependabot covers uv, Docker and Actions.
- **No data downloads at runtime:** `textstat` silently downloads the NLTK cmudict through NLTK whenever it is missing. The image fetches it at build time into a root-owned `/opt/nltk_data`, and `APP_ENV=prod` makes startup fail if it is absent instead of downloading while serving documents. Verified by starting the image with the network disabled.
- **Sandbox memory limit:** the Linux test showed the limit does bind (a 32 MB cap kills the child; the parser alone needs about 60 MB of address space, so 512 MB leaves wide headroom). `PARSE_MEMORY_MB` may now be as low as 16 so the limit can be tested.
- **Cheaper child:** profiling showed 0.55 s of a 0.63 s sandbox start-up was importing pydantic-settings. The child now receives its validation limits as JSON and never imports the settings machinery, while still validating independently of its caller.
**Consequences:** Load testing 10 concurrent rules-only audits against the hardened container gave 60 of 60 successes with no errors, but p95 of 3.56 s before the child was slimmed, against a 3 s target. A clean re-measurement after the change was not possible while a background installer saturated the host CPU, so the target is not yet confirmed (see the roadmap). Each audit still pays for a fresh interpreter start; a pre-forked, pre-imported worker pool would remove most of that cost if the target stays out of reach on a small host. Trivy is verified by CI only: a local run through an external scanner image was not permitted in this environment. The base-image digest must be updated deliberately (Dependabot proposes it).

## ADR-016 — First real-model results and what the providers taught us
**Date:** 2026-11-04 · **Status:** Accepted
**Context:** The LLM layer was built and tested with a fake model (ADR-012). Real keys and models exposed things a fake could not.
**Decision and findings:**
- **Model availability:** the provider's model list shows names that exist, not names a new account may use. `gemini-2.5-flash-lite` and `gemini-2.5-flash` were listed but return 404 ("no longer available to new users"). Verify a model with a real call, including an image call for vision, before configuring it. Avoid `-latest` aliases: they change under you and make eval results hard to reproduce.
- **Schema keywords:** Gemini's structured-output mode rejects `maxItems` with a vague "invalid argument" (Groq accepts it). The `results` list cap is therefore enforced in code (`MAX_RESULTS`, extra answers ignored), a test forbids `maxItems` and `minItems` in the schema, and string and number limits stay in the schema.
- **Determinism:** Gemini 3.x ignores the temperature setting ("fixed sampling defaults"), so results can differ between runs. Treat single-run eval numbers as indicative and re-run before relying on them.
- **Vision matters:** on a document with one wrong and one correct alt text, Gemini with the image flagged only the wrong one; Groq, working from text alone, flagged both. Text-only fallback is a real accuracy loss, which is why its confidence is lowered by 0.2.
- **Results (19 synthetic documents, one run):** agreement 92.9% (13 matched, 0 missed, 1 false alarm) against an 80% target; 0 of 5 injection documents succeeded; 18 calls and about 27K tokens in total. The false alarm was Gemini judging a plain "Bar chart of four bars that rise from 9 to 59" alt text as describing structure, not meaning.
**Consequences:** The injection result is weak evidence: two injection documents sent nothing for review (hidden text and a table cell are not selected as items) and one hid its payload in an image title, which is not sent, so only some payloads reached the model. Before the injection checklist item is ticked, add injection documents whose payloads are guaranteed to be sent (inside link text, alt text and jargon paragraphs) and re-run. Free-tier limits are still unrecorded.

## ADR-017 — Web UI design: accessible by our own rules, safe by construction
**Date:** 2026-11-04 · **Status:** Accepted
**Context:** The first UI was a plain Streamlit form, and on a wide desktop screen it looked unfinished (half-empty hero, a disabled button with unreadable text, mismatched card titles). A product that audits accessibility has to meet its own standard.
**Decision:**
- **Design system in one place** (`ui/theme.py`): palette, severity styles, score bands and the stylesheet. Every text-on-background pair is listed in `CONTRAST_PAIRS`, and a test checks each one with `accesslens.rules.color.contrast_ratio` (AA, 4.5:1). Colour is never the only signal: severity is spelled out in a chip, the score carries a word ("Excellent", "Good", "Needs work", "Poor"), and the score ring has an accessible name.
- **Safe markup** (`ui/components.py`): the only place HTML is built. Everything that comes from a document or the API goes through `html.escape`; WCAG links are limited to `https://www.w3.org/` and open with `rel="noopener noreferrer"`; numbers are coerced to `int`. Tests feed hostile text (script tags, event-handler attributes) and require that none survives.
- **Layout:** a hero with a static example result (labelled as an example, hidden from assistive technology), a form panel with a sample button, results with a score card, four severity cards, severity filters and search, findings grouped by rule (critical and high groups open by default, 15 shown per group), and report downloads. HTML and XLSX are produced only when clicked (lazy `download_button` data), so a check makes two API calls, not four. AI review is off by default.
- **Bundled sample** (`ui/samples/sample-quarterly-report.docx`, synthetic, generated by `eval/generate_corpus.py`): one click shows every severity and lets the UI be tried and tested without a file picker.
**Consequences:** Streamlit does not reload imported helper modules in a running server, so after changing `theme.py` or `components.py` the UI process must be restarted (a stale process kept serving old CSS and hid a fixed bug). The design was checked in a narrow preview and by DOM measurements, not in a full-width browser, and not on a phone. The hero preview is hand-written, so it must be updated if the scoring or wording changes. Update: after a check the page becomes a two-pane workspace (form, score, filters and downloads on the left, findings on the right, container up to 1560px), because the single narrow column looked like a phone app on a laptop.

## ADR-018 — PowerPoint (.pptx) support through the same engine
**Date:** 2026-11-04 · **Status:** Accepted
**Context:** Word is where most inaccessible documents start, but presentations are next, and they share the Office Open XML package format. A second format also tests whether the architecture is really format-independent.
**Decision:**
- **No new dependency.** `parse_pptx.py` reads the package with the standard `zipfile` module and the hardened `lxml` parser that validation already uses, instead of adding `python-pptx` (which would also bring Pillow and XlsxWriter). The attack surface and supply chain stay as they were.
- **One validation path.** `validate_upload` accepts exactly one of the two main content types and returns the format; a package claiming both, macro-enabled presentations and DOCTYPE declarations are rejected as before. `validate_docx` stays for callers that need Word only. The sandbox child validates again and dispatches on the format, so parsing still runs in the same subprocess with the same limits.
- **Same model.** A slide becomes a title block (always present, empty if there is no title) followed by its text, pictures and tables in shape-tree order, which is the screen-reader order. `ParsedDocument` gains `slides`, `Block.slide`, `DocMeta.kind` and `Location.slide`. Footer, date and slide-number placeholders are not content.
- **Rules declare their format.** `kinds_for` maps rule ids to formats: five new `SLD-` rules for slides, ten Word-only rules, the rest shared. CLR-001 stays Word-only because a themed slide does not state its background, so white text on a dark slide would be reported as unreadable.
- **MCP tool name kept.** `audit_docx` still exists for compatibility and now also accepts `.pptx` paths.
**Consequences:** Rules eval on the synthetic corpus: 100% recall and precision over 67 documents (27 are decks). The decks and the parser were written together, so that shows internal consistency, not accuracy on real decks. Running the parser on seven real PowerPoint-structured templates found two false-positive sources the synthetic decks could not (empty footer placeholders, and a slide-number placeholder placed before the title); both are fixed and the footer case is covered by a test. The remaining findings on those templates (missing document title, small text, text before the title) are plausible but unlabelled, so no accuracy is claimed for them. Not covered: charts, SmartArt, media, animations, inherited text sizes and visual contrast.
