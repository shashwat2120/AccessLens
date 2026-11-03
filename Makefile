.PHONY: setup lint type test eval eval-llm corpus audit-deps run-api run-ui run-mcp

run-api:
	uv run uvicorn --factory accesslens.api.main:app_factory --host 127.0.0.1 --port 8000

run-ui:
	uv run streamlit run ui/streamlit_app.py

run-mcp:
	uv run python -m accesslens.mcp_server.server

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

# Rules-only eval (LLM off); fails if recall, precision or false positives miss the targets.
eval: corpus
	uv run python eval/run_eval.py --check --out eval/results/tmp

# Real LLM calls: needs keys and model names in .env; spends free-tier quota.
eval-llm: corpus
	uv run python eval/run_eval_llm.py --check

audit-deps:
	uv run pip-audit
