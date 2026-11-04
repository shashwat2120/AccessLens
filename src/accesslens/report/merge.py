"""Combine rule and LLM findings (TRD §4 ``merge``)."""

from accesslens.llm.checks import Rewrite, apply_rewrites
from accesslens.models import Finding
from accesslens.report.prioritize import prioritize


def merge_findings(
    rule_findings: list[Finding], llm_findings: list[Finding], rewrites: list[Rewrite]
) -> list[Finding]:
    """Additive merge: rule findings are never removed, only their suggestion text can change.

    Identical findings (same rule, block and message) collapse into one, kept from the most
    confident copy, and the message says how many there were so the count is not hidden. Then
    everything is put in priority order.
    """
    combined = apply_rewrites(rule_findings, rewrites) + llm_findings
    groups: dict[tuple[str, str, str], list[Finding]] = {}
    for finding in sorted(combined, key=lambda f: -f.confidence):
        key = (finding.rule_id, finding.location.block_id, finding.message)
        groups.setdefault(key, []).append(finding)

    unique: list[Finding] = []
    for group in groups.values():
        kept = group[0]
        if len(group) > 1:
            kept = kept.model_copy(
                update={"message": f"{kept.message} (found {len(group)} times in this block)"}
            )
        unique.append(kept)
    return prioritize(unique)
