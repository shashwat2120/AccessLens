"""The rules-only eval must meet the targets in docs/05-EVALUATION.md."""

from pathlib import Path

from run_eval import TARGETS, evaluate, failed_targets


def test_rules_meet_the_accuracy_targets(corpus: tuple[Path, Path]) -> None:
    result = evaluate(corpus[0], corpus[1])
    assert not failed_targets(result), (result["metrics"], result["misses"], result["spurious"])
    assert result["documents"] == 67  # 40 Word documents and 27 decks
    assert result["metrics"]["recall"] >= TARGETS["recall"]
