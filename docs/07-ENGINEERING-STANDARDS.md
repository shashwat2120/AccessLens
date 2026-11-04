# 07 — Engineering Standards

**Status:** v1.0 · **Last updated:** 2026-11-03

## Code
- Python 3.12, fully type-hinted; `mypy --strict` passes.
- `ruff` for lint + format (rules: E, F, I, B, UP, S, SIM, RUF).
- Small pure functions; a rule's check is `(ParsedDocument, RuleConfig) -> list[Hit]` with no I/O; `Rule.run` turns hits into `Finding`s (ADR-011).
- No business logic in `api/`, `cli.py`, `mcp_server/`, or `ui/` — they call `AuditService`.
- No hard-coded model names, limits, keys, or URLs — everything via `config.py`.
- Errors: raise typed exceptions from `errors.py`; map to problem+json in one place.
- No `print`; use the logger. Never log document content (SECURITY §6).
- Docstrings on public functions; comments explain *why*, not *what*.

## Testing
| Layer | What | Where |
|---|---|---|
| Unit | Each rule, validator, redactor, scorer | `tests/unit` |
| Integration | Pipeline over corpus, API with TestClient, MCP tool calls | `tests/integration` |
| Security | Malicious files, injection, headers, auth, path traversal, XLSX/HTML escaping | `tests/security` |
| Eval | Accuracy targets | `eval/` |

- Coverage ≥ 85% for `rules/`, `ingest/`, `report/`, `llm/redact.py`; ≥ 75% overall.
- Unit/integration tests never call real LLMs — use a fake chat model. Real calls only in `make eval-llm`.
- Every bug fix comes with a test that would have caught it.

## Git workflow
- `main` is protected; work on `feat/…`, `fix/…`, `docs/…` branches; PRs even when solo (CI must pass).
- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`, `refactor:`, `security:`).
- Semantic versioning; `CHANGELOG.md` updated per release.

## CI (`.github/workflows/ci.yml`) — runs on every PR
1. `uv sync --frozen`
2. `ruff check` + `ruff format --check`
3. `mypy`
4. `pytest` with coverage gate
5. Rules-only eval with accuracy gate
6. `pip-audit`, `bandit`, `gitleaks`
7. Docker build, hardened-container smoke test and Trivy scan (every PR and push; Trivy runs as the pinned official container, see ADR-015)

## Makefile targets
`make setup | lint | type | test | eval | eval-llm | corpus | run-api | run-ui | run-mcp | docker | audit-deps`

## Observability
- JSON logs with `request_id`, `file_sha256`, `size_bytes`, `mode`, per-node `duration_ms`, `findings_by_severity`, `llm_calls`, `llm_tokens`, `degraded`.
- `/healthz` and `/readyz` for the host platform.
- Track free-tier quota usage from logs; alert yourself (e.g., platform log alert) if 429s spike.

## Documentation rules
- Docs in `docs/` are the source of truth. If code and docs disagree, fix one of them in the same PR.
- Any significant choice gets an entry in `08-DECISIONS.md`.
- Tick roadmap boxes in the PR that completes them.

## Definition of Done (any task)
- [ ] Code + tests, CI green
- [ ] No new security warnings
- [ ] Docs updated (catalog, TRD, decisions, roadmap) if affected
- [ ] No secrets, no document content in logs or fixtures beyond synthetic data
