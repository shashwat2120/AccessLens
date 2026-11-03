# CLAUDE.md — AccessLens

AccessLens audits Word (.docx) files for accessibility issues and produces a prioritized remediation report. Rules handle clear-cut checks; an LLM handles judgment calls. Production quality and security are requirements, not extras.

## Read before working
1. `docs/06-ROADMAP.md` — find the current phase; work only on that phase unless told otherwise.
2. `docs/02-TRD.md` — architecture, data model, interfaces, repo layout.
3. `docs/03-SECURITY.md` — every [MUST] applies to any code you touch.
4. `docs/04-RULES-CATALOG.md` — when implementing or changing rules.
5. `docs/07-ENGINEERING-STANDARDS.md` — code, test, and git conventions.
`docs/01-PRD.md` (scope) and `docs/08-DECISIONS.md` (why) as needed.

## Non-negotiables
- Never commit secrets. Keys come from `.env` via `config.py` (`SecretStr`).
- Never log or print document content, alt text, filenames, or image bytes.
- Treat every uploaded document as hostile: validate before parsing, parse in the sandbox.
- The LLM gets no tools. Document text goes only inside `<document_item>` tags. LLM output is schema-validated and may only add findings for its allowed rule IDs.
- Unit/integration tests use a fake LLM — never real API calls.
- Business logic lives in `src/accesslens/` core modules and is reached through `AuditService`; API/CLI/MCP/UI stay thin.
- No hard-coded model names, limits, or URLs.

## Workflow
- Small, focused changes with tests. Run `make lint type test eval` before saying a task is done.
- Ask before adding a new dependency, and record notable choices in `docs/08-DECISIONS.md`.
- If code and docs disagree, point it out and fix one of them in the same change.
- Tick the matching boxes in `docs/06-ROADMAP.md` when a task is complete.
- Commit messages follow Conventional Commits.

## Commands
`make setup` · `make lint` · `make type` · `make test` · `make eval` · `make eval-llm` · `make corpus` · `make run-api` · `make run-ui` · `make run-mcp`
