import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from accesslens.models import Finding, Location, Severity, Source, WcagLevel
from accesslens.report.prioritize import count_by_severity, prioritize
from accesslens.report.score import compute_score
from accesslens.rules import REGISTRY, run_rules
from accesslens.rules.base import Hit, Rule
from factories import block, doc, heading, image

ROOT = Path(__file__).resolve().parents[2]


def finding(
    rule_id: str, severity: Severity, level: WcagLevel = WcagLevel.A, order: int = 0
) -> Finding:
    return Finding(
        id=f"{rule_id}-{order}",
        rule_id=rule_id,
        title="t",
        severity=severity,
        wcag_criterion=None,
        wcag_level=level,
        location=Location(block_id=f"b{order:04d}", block_order=order, snippet=""),
        message="m",
        suggestion="s",
        source=Source.RULE,
    )


def catalog_rows() -> dict[str, list[str]]:
    text = (ROOT / "docs" / "04-RULES-CATALOG.md").read_text(encoding="utf-8")
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if re.fullmatch(r"[A-Z]{3}-\d{3}", cells[0]) and len(cells) == 5:
            rows[cells[0]] = cells
    return rows


def test_registry_matches_the_catalog() -> None:
    rows = catalog_rows()
    assert set(REGISTRY) <= set(rows)
    for rule_id, rule in REGISTRY.items():
        assert rule.severity.value == rows[rule_id][3].lower(), rule_id
    llm_only = set(rows) - set(REGISTRY)
    assert llm_only == {"IMG-003", "LNK-003", "TXT-006"}


@pytest.fixture
def crashing_rule() -> Iterator[None]:
    def explode(*_: object) -> list[Hit]:
        raise RuntimeError("secret document text")

    REGISTRY["ZZZ-999"] = Rule(
        "ZZZ-999", "t", Severity.LOW, None, WcagLevel.BEST_PRACTICE, 1.0, explode
    )
    yield
    del REGISTRY["ZZZ-999"]


@pytest.mark.usefixtures("crashing_rule")
def test_a_crashing_rule_is_reported_without_stopping_others() -> None:
    document = doc([block(0, "text")], title=None)
    findings, warnings = run_rules(document)
    assert warnings == ["Rule ZZZ-999 failed and was skipped."]
    assert "secret" not in " ".join(warnings)
    assert any(f.rule_id == "DOC-001" for f in findings)


def test_finding_ids_are_unique_and_snippets_are_safe() -> None:
    long_text = "bad\x00text\x1b " + "x" * 300
    document = doc(
        [heading(0, "A"), block(1, long_text, "image")],
        images=[image(1, alt_text=None), image(1, id="i002", alt_text=None)],
    )
    findings, _ = run_rules(document, only={"IMG-001"})
    assert len(findings) == 2
    assert len({f.id for f in findings}) == 2
    snippet = findings[0].location.snippet
    assert len(snippet) <= 120
    assert "\x00" not in snippet
    assert "\x1b" not in snippet


def test_prioritize_orders_by_severity_level_frequency_then_position() -> None:
    findings = [
        finding("LOW-1", Severity.LOW, order=1),
        finding("MED-1", Severity.MEDIUM, order=9),
        finding("CRIT-1", Severity.CRITICAL, order=5),
        finding("MED-2", Severity.MEDIUM, WcagLevel.AA, order=1),
        finding("MED-3", Severity.MEDIUM, order=2),
        finding("MED-3", Severity.MEDIUM, order=3),
    ]
    ordered = [f.rule_id for f in prioritize(findings)]
    assert ordered == ["CRIT-1", "MED-3", "MED-3", "MED-1", "MED-2", "LOW-1"]
    assert findings[0].rule_id == "LOW-1"  # input untouched


def test_count_by_severity_includes_zeroes() -> None:
    counts = count_by_severity([finding("A", Severity.HIGH)])
    assert counts == {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 0,
        Severity.LOW: 0,
    }


def test_score_formula() -> None:
    assert compute_score([]) == 100
    assert compute_score([finding("A", Severity.CRITICAL)]) == 83  # 100 - 10 * 100 / 60
    many_low = [finding("L", Severity.LOW, order=i) for i in range(50)]
    assert compute_score(many_low) == 92  # capped at 5 per rule: 100 - 5 * 100 / 60
    disaster = [finding(f"C{i}", Severity.CRITICAL) for i in range(20)]
    assert compute_score(disaster) == 0
