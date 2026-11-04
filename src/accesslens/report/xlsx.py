"""XLSX export (SECURITY §9): document-derived cells cannot be read as formulas."""

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.cell.cell import Cell

from accesslens.models import Report

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
_CONTROL = {c: " " for c in range(32) if chr(c) not in "\n"}


def safe_cell(value: Any) -> Any:
    """Neutralise formula injection: text starting with = + - @ tab or CR gets a leading '."""
    if not isinstance(value, str):
        return value
    text = value.translate(_CONTROL)
    if value.startswith(_FORMULA_STARTS):
        return "'" + text
    return text


def _write(cell: Cell, value: Any) -> None:
    cell.value = safe_cell(value)
    if isinstance(cell.value, str):
        cell.data_type = "s"  # a string, whatever it looks like


def render_xlsx(report: Report) -> bytes:
    workbook = Workbook()
    summary = workbook.create_sheet("Summary", 0)
    workbook.remove(workbook["Sheet"])  # the default empty sheet
    rows: list[tuple[str, Any]] = [
        ("Score (0-100)", report.score),
        ("Mode", report.mode),
        ("Generated (UTC)", report.generated_at.strftime("%Y-%m-%d %H:%M")),
        ("File fingerprint (SHA-256, first 12)", report.meta.sha256[:12]),
        ("Words", report.meta.word_count),
        ("Images", report.meta.image_count),
        ("Tables", report.meta.table_count),
        *[(f"{severity.value.capitalize()} findings", n) for severity, n in report.counts.items()],
        *[("Note", warning) for warning in report.warnings],
    ]
    for row in rows:
        summary.append([None, None])
        _write(summary.cell(summary.max_row, 1), row[0])
        _write(summary.cell(summary.max_row, 2), row[1])

    findings = workbook.create_sheet("Findings")
    headers = [
        "Severity",
        "Rule",
        "Title",
        "WCAG",
        "Level",
        "Block",
        "Snippet",
        "Problem",
        "How to fix",
        "Source",
        "Confidence",
        "Slide",
    ]
    findings.append(headers)
    for finding in report.findings:
        findings.append([None] * len(headers))
        values = [
            finding.severity.value,
            finding.rule_id,
            finding.title,
            finding.wcag_criterion or "best practice",
            finding.wcag_level.value,
            finding.location.block_order,
            finding.location.snippet,
            finding.message,
            finding.suggestion,
            finding.source.value,
            finding.confidence,
            finding.location.slide,
        ]
        for column, value in enumerate(values, start=1):
            _write(findings.cell(findings.max_row, column), value)
    findings.freeze_panes = "A2"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
