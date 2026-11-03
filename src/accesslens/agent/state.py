"""State passed between pipeline nodes (TRD §4)."""

from typing import Literal, TypedDict

from accesslens.llm.checks import LlmOutcome
from accesslens.llm.items import LlmItem
from accesslens.models import AuditOptions, Finding, ParsedDocument, Report


class AuditState(TypedDict, total=False):
    request_id: str
    file_bytes: bytes
    options: AuditOptions
    mode: Literal["full", "rules_only"]  # effective mode after configuration is applied
    sha256: str
    parsed: ParsedDocument
    rule_findings: list[Finding]
    llm_items: list[LlmItem]
    llm_outcome: LlmOutcome
    findings: list[Finding]
    warnings: list[str]
    timings: dict[str, float]  # node name -> milliseconds
    report: Report
