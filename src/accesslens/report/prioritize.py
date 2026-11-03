"""Finding order (TRD §6): severity, then WCAG level, then how common the rule is, then position."""

from collections import Counter

from accesslens.models import Finding, Severity, WcagLevel

SEVERITY_RANK = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
LEVEL_RANK = {WcagLevel.A: 0, WcagLevel.AA: 1, WcagLevel.AAA: 2, WcagLevel.BEST_PRACTICE: 3}


def prioritize(findings: list[Finding]) -> list[Finding]:
    """Return findings sorted most important first; the input is not modified."""
    occurrences = Counter(f.rule_id for f in findings)
    return sorted(
        findings,
        key=lambda f: (
            SEVERITY_RANK[f.severity],
            LEVEL_RANK[f.wcag_level],
            -occurrences[f.rule_id],
            f.location.block_order,
            f.id,
        ),
    )


def count_by_severity(findings: list[Finding]) -> dict[Severity, int]:
    counts = Counter(f.severity for f in findings)
    return {severity: counts.get(severity, 0) for severity in Severity}
