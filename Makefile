.PHONY: setup lint type test eval corpus audit-deps

corpus:
	uv run python eval/generate_corpus.py

setup:
	uv sync
	uv run pre-commit install

lint:
	uv run ruff check .
	uv run ruff format --check .

type:
	uv run mypy

test:
	uv run pytest --cov

# Rules-only eval arrives in Phase 3.
eval:
	@echo "eval: not implemented until Phase 3"

audit-deps:
	uv run pip-audit
