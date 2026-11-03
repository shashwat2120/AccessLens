"""0-100 accessibility score (TRD §6).

``score = max(0, round(100 - sum(weight * min(count_per_rule, cap)) * 100 / normalizer))``.
Capping the count per rule stops one repeated issue from zeroing the score. The normalizer is
tuned against the eval corpus.
"""

from collections import Counter

from accesslens.models import Finding, Severity

WEIGHTS = {Severity.CRITICAL: 10, Severity.HIGH: 5, Severity.MEDIUM: 2, Severity.LOW: 1}
FORMULA = (
    "100 minus the weighted issue count (critical 10, high 5, medium 2, low 1; at most 5 "
    "counted per rule), scaled by {normalizer}, never below 0."
)


def compute_score(findings: list[Finding], *, normalizer: int = 60, per_rule_cap: int = 5) -> int:
    """Score a set of findings; no findings scores 100."""
    per_rule: Counter[str] = Counter(f.rule_id for f in findings)
    severity_of = {f.rule_id: f.severity for f in findings}
    penalty = sum(
        WEIGHTS[severity_of[rule_id]] * min(count, per_rule_cap)
        for rule_id, count in per_rule.items()
    )
    return max(0, round(100 - penalty * 100 / normalizer))
