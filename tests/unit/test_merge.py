import tomllib
from pathlib import Path

from accesslens.models import Finding, Location, Severity, Source, WcagLevel
from accesslens.report.merge import merge_findings

ROOT = Path(__file__).resolve().parents[2]


def finding(rule_id: str, block: int, *, n: int = 0, message: str = "Problem.") -> Finding:
    return Finding(
        id=f"{rule_id}-b{block:04d}-{n}",
        rule_id=rule_id,
        title="t",
        severity=Severity.LOW,
        wcag_criterion=None,
        wcag_level=WcagLevel.A,
        location=Location(block_id=f"b{block:04d}", block_order=block, snippet=""),
        message=message,
        suggestion="Fix it.",
        source=Source.RULE,
    )


def test_identical_findings_in_a_block_fold_into_one_with_a_count() -> None:
    merged = merge_findings([finding("LNK-002", 5, n=i) for i in range(4)], [], [])
    assert len(merged) == 1
    assert merged[0].message == "Problem. (found 4 times in this block)"


def test_single_findings_and_different_blocks_are_left_alone() -> None:
    merged = merge_findings(
        [finding("LNK-002", 5), finding("LNK-002", 6), finding("TXT-002", 5)], [], []
    )
    assert len(merged) == 3
    assert all("found" not in f.message for f in merged)


def test_different_messages_in_the_same_block_stay_separate() -> None:
    merged = merge_findings(
        [
            finding("TXT-002", 5, message="A sentence has 31 words."),
            finding("TXT-002", 5, message="A sentence has 40 words."),
        ],
        [],
        [],
    )
    assert len(merged) == 2


def test_the_ui_upload_limit_matches_the_api_default() -> None:
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["server"]["maxUploadSize"] == 10
