"""The LLM eval runs end to end on the real corpus with a fake model (no real calls)."""

from pathlib import Path

from run_eval_llm import evaluate_llm, failed_targets

from accesslens.config import Settings
from fakes import echo, no_wait_limiters, provider


def test_llm_eval_pipeline_runs_with_a_fake_model(corpus: tuple[Path, Path]) -> None:
    settings = Settings(_env_file=None, llm_budget_per_doc=50)
    fake, model = provider(echo(issue=True, confidence=0.95))
    result = evaluate_llm(corpus[0], corpus[1], [fake], settings, limiters=no_wait_limiters())
    assert result["documents"] >= 19
    assert model.calls
    # A model that flags everything finds every planted LLM issue but also makes false alarms.
    assert result["metrics"]["recall"] > 0.9
    assert result["metrics"]["precision"] < 1.0
    assert result["usage"]["calls"] > 0
    assert failed_targets(result)  # agreement is far below target, so the gate would fail


def test_a_model_that_never_flags_has_no_false_positives(corpus: tuple[Path, Path]) -> None:
    settings = Settings(_env_file=None, llm_budget_per_doc=50)
    fake, _ = provider(echo(issue=False))
    result = evaluate_llm(corpus[0], corpus[1], [fake], settings, limiters=no_wait_limiters())
    assert result["metrics"]["false_positives_per_clean_doc"] == 0
    assert result["metrics"]["recall"] == 0
    # Missing planted LLM issues in injection docs counts as an injection failure.
    assert result["metrics"]["injection_failures"] >= 1
