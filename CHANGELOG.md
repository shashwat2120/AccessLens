# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Rule engine with 23 deterministic checks mapped to WCAG 2.2, finding prioritisation and a
  0-100 score (Phase 3).
- LLM review of alt text, link text and jargon, plus plain-language rewrites, with PII redaction,
  schema-validated output restricted to allowed rules, retries, provider fallback, a per-document
  call budget and a rules-only degraded mode (Phase 4).
- LangGraph audit pipeline behind a single `AuditService`, with JSON logs that never contain
  document content (Phase 5).
- CLI, REST API (API keys, rate limits, size limits, problem+json errors, security headers,
  CORS), HTML and XLSX reports, MCP server and Streamlit UI (Phase 6).
- Secure ingest: upload validation, a subprocess sandbox with time and memory limits, and a
  `python-docx` parser (Phase 2).
- Evaluation corpus generator, answer key, rules-only eval gate and LLM eval script (Phases 1,
  3 and 4).
- Multi-stage, non-root, read-only-filesystem Docker images (API and UI) with a digest-pinned
  base, a container smoke test and Trivy scanning in CI, Dependabot, a load-test script and the
  repository `SECURITY.md` (Phase 7).

- PowerPoint (.pptx) support: validation, sandboxed parsing without a new dependency, five slide rules (title, duplicate title, reading order, small text, empty placeholder), slide numbers in findings, a sample deck in the UI and 27 decks in the eval corpus. Word-only rules no longer run on slides.

### Changed
- After a check the web UI becomes a wide two-pane workspace (form, score and filters on the left, findings on the right) instead of one narrow column.
- The web UI is redesigned as a product: a hero with an example result, a clear upload panel with
  a "Try a sample document" button, a score ring with a word, colour-coded severity cards,
  filters, findings grouped by rule with linked WCAG references, and report downloads. Every
  colour pair is checked against WCAG AA with AccessLens's own contrast function, and all
  document text is escaped before it reaches the page.
- Identical findings in one block are folded into one that says how many there were.
- The production API now writes JSON logs; the UI enforces the same 10 MB upload limit as the API.
- Rate limiting uses the `limits` library as pre-authentication dependencies instead of
  slowapi, so failed logins are throttled too.
- The sandbox child no longer imports the settings machinery; it receives its validation limits
  directly, which removes about half a second from every audit.

### Security
- Production never downloads data at runtime: the readability dictionary is baked into the
  image, and `APP_ENV=prod` refuses to start without it.
- The sandbox memory limit is covered by a test that runs on Linux.
