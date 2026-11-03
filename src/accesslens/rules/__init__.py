"""Deterministic accessibility rules. Importing this package registers every rule."""

import logging

from accesslens.models import Finding, ParsedDocument
from accesslens.rules import (  # noqa: F401 - imported for their @rule registrations
    color,
    document,
    headings,
    images,
    links,
    lists,
    tables,
    text,
)
from accesslens.rules.base import REGISTRY, Rule, RuleConfig

__all__ = ["REGISTRY", "Rule", "RuleConfig", "run_rules"]

logger = logging.getLogger(__name__)


def run_rules(
    doc: ParsedDocument,
    config: RuleConfig | None = None,
    only: set[str] | None = None,
) -> tuple[list[Finding], list[str]]:
    """Run every (or the selected) rule; one crashing rule is reported, not fatal."""
    cfg = config or RuleConfig()
    findings: list[Finding] = []
    warnings: list[str] = []
    for rule_id, rule in sorted(REGISTRY.items()):
        if only is not None and rule_id not in only:
            continue
        try:
            findings.extend(rule.run(doc, cfg))
        except Exception as exc:
            # Log the type only: exception messages can echo document content.
            logger.error("rule_failed rule_id=%s error=%s", rule_id, type(exc).__name__)
            warnings.append(f"Rule {rule_id} failed and was skipped.")
    return findings, warnings
