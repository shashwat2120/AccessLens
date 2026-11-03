# 01 — Product Requirements Document (PRD)

**Product:** AccessLens — Content Accessibility Audit Agent
**Owner:** Shashwat Mishra
**Status:** Draft v1.0
**Last updated:** 2026-11-03

---

## 1. Problem

Course teams publish large amounts of Word (.docx) content to LMS platforms. Accessibility issues — missing alt text, broken heading structure, unreadable link text, low-contrast text, overly complex language — are common, and accessibility requirements keep growing. Manual review is slow, inconsistent, and depends on reviewer expertise. Teams need a fast, reliable way to find issues and know what to fix first.

## 2. Goal

Given one or more .docx files, AccessLens produces a **prioritized remediation report**: every accessibility issue found, where it is, why it matters (mapped to WCAG 2.2), and a concrete suggested fix.

## 3. Target users

| User | Need |
|---|---|
| Instructional designer | Check a course document before publishing; get specific fixes |
| Content reviewer / QA | Audit a batch of files consistently and export findings |
| Developer / AI tool user | Call the checker from Claude or another MCP client, or via API |

## 4. Scope

### In scope (v1)
- Input: **.docx only** (Word 2007+). Single file or batch (up to 20 files per request).
- Rule-based checks for clear-cut issues (see `04-RULES-CATALOG.md`).
- LLM-based checks for judgment calls: alt text quality (with image understanding), reading level rewrites, ambiguous link text.
- Prioritized report: JSON, HTML, and Excel (.xlsx) export.
- Accessibility score (0–100) per document.
- Interfaces: REST API, CLI, MCP server, Streamlit web UI.
- "Rules-only" mode that never sends content to an LLM.

### Out of scope (v1) — non-goals
- PowerPoint, PDF, HTML, or video/audio files.
- Automatically fixing / rewriting the source document (we suggest fixes; the user applies them).
- User accounts, teams, or saved history (no persistent storage of documents).
- Full WCAG conformance certification. AccessLens is an assistive audit tool, not a legal compliance guarantee.
- Screen reader simulation.

## 5. Features & requirements

| ID | Requirement | Priority |
|---|---|---|
| F1 | Upload .docx via UI/API/CLI/MCP; reject anything else safely | Must |
| F2 | Parse document into a normalized structure (headings, paragraphs, lists, tables, images, links, metadata) | Must |
| F3 | Run all rule checks in `04-RULES-CATALOG.md` | Must |
| F4 | Run LLM checks only on items rules cannot judge, within a per-document budget | Must |
| F5 | Judge alt text against the actual image (vision) | Should |
| F6 | Each finding has: rule ID, severity, WCAG criterion + level, location, snippet, message, suggested fix, source (rule/llm), confidence | Must |
| F7 | Prioritize findings (severity → WCAG level → frequency) and compute a score | Must |
| F8 | Export JSON / HTML / XLSX | Must |
| F9 | Batch mode with a combined summary | Should |
| F10 | MCP server exposing audit tools | Must |
| F11 | Rules-only mode (no LLM calls) | Must |
| F12 | Provider-swappable LLM layer (Gemini primary, Groq fallback) | Must |
| F13 | Configurable target reading grade level | Could |

## 6. User flow (web UI)

1. User opens the app, sees a notice about what data is sent to the LLM provider and a "Rules-only" toggle.
2. Uploads one or more .docx files.
3. Sees progress, then a report: score, counts by severity, and a sorted list of findings with fixes.
4. Downloads HTML or XLSX report.
5. Nothing is stored after the response is returned.

## 7. Success metrics

| Metric | Target |
|---|---|
| Recall on planted rule-detectable issues (eval corpus) | ≥ 98% |
| Precision of rule findings | ≥ 95% |
| LLM finding agreement with human labels | ≥ 80% |
| Prompt-injection test docs that alter results | 0 |
| p95 audit time, 20-page doc, LLM on | ≤ 45 s |
| p95 audit time, rules-only | ≤ 3 s |
| LLM calls per document | ≤ budget (default 10) |
| Cost per document | $0 on free tier |

Full method in `05-EVALUATION.md`.

## 8. Constraints & assumptions
- Must run on free LLM tiers (rate limits apply — see `08-DECISIONS.md`, ADR-003).
- Documents may contain sensitive content; privacy controls in `03-SECURITY.md` are mandatory, not optional.
- Single developer, ~5 weeks part-time (`06-ROADMAP.md`).

## 9. Risks

| Risk | Mitigation |
|---|---|
| Free-tier rate limits hit during demo | Batch items per LLM call, cache results, fallback provider, rules-only mode |
| LLM gives wrong or inconsistent judgments | Rules handle clear cases; LLM output is schema-validated and labeled with confidence; measured in eval |
| Malicious documents | Validation and sandboxed parsing (`03-SECURITY.md`) |
| Free-tier provider may use prompts to improve its products | Clear UI notice, rules-only mode, PII redaction |

## 10. Release criteria (v1.0)
- All "Must" requirements done.
- Eval targets in section 7 met and published in README.
- Security checklist in `03-SECURITY.md` fully ticked.
- CI green; deployed demo reachable over HTTPS.
