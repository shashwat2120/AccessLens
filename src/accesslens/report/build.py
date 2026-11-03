"""Assemble the final ``Report``."""

from datetime import UTC, datetime
from typing import Literal

from accesslens.models import Finding, LlmUsage, ParsedDocument, Report
from accesslens.report.prioritize import count_by_severity
from accesslens.report.score import compute_score


def build_report(
    parsed: ParsedDocument,
    findings: list[Finding],
    *,
    mode: Literal["full", "rules_only"],
    usage: LlmUsage | None,
    warnings: list[str],
) -> Report:
    return Report(
        generated_at=datetime.now(UTC),
        meta=parsed.meta,
        score=compute_score(findings),
        counts=count_by_severity(findings),
        findings=findings,
        llm=usage,
        mode=mode,
        warnings=warnings,
    )
