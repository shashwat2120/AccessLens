"""Combine rule and LLM findings (TRD §4 ``merge``)."""

from accesslens.llm.checks import Rewrite, apply_rewrites
from accesslens.models import Finding
from accesslens.report.prioritize import prioritize


def merge_findings(
    rule_findings: list[Finding], llm_findings: list[Finding], rewrites: list[Rewrite]
) -> list[Finding]:
    """Additive merge: rule findings are never removed, only their suggestion text can change.

    Exact duplicates (same rule, block and message) collapse to the most confident copy, then
    everything is put in priority order.
    """
    combined = apply_rewrites(rule_findings, rewrites) + llm_findings
    seen: set[tuple[str, str, str]] = set()
    unique: list[Finding] = []
    for finding in sorted(combined, key=lambda f: -f.confidence):
        key = (finding.rule_id, finding.location.block_id, finding.message)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return prioritize(unique)
