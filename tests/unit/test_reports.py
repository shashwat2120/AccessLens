import io
from datetime import UTC, datetime
from typing import Any

import pytest
from openpyxl import load_workbook

from accesslens.llm.checks import LLM_RULES
from accesslens.models import (
    DocMeta,
    Finding,
    Location,
    Report,
    Severity,
    Source,
    WcagLevel,
)
from accesslens.report.html import HTML_CSP, render_html
from accesslens.report.xlsx import render_xlsx, safe_cell
from accesslens.rules import REGISTRY
from accesslens.rules.catalog import get_rule, rule_catalog

HOSTILE = [
    '=HYPERLINK("http://evil.example","x")',
    "+cmd|' /C calc'!A0",
    "-2+3",
    "@SUM(A1:A9)",
    "\t=1+1",
    "\r=1+1",
]


def make_report(**finding_kw: Any) -> Report:
    base: dict[str, Any] = {
        "id": "IMG-001-b0001",
        "rule_id": "IMG-001",
        "title": "Image has no alt text",
        "severity": Severity.CRITICAL,
        "wcag_criterion": "1.1.1",
        "wcag_level": WcagLevel.A,
        "location": Location(block_id="b0001", block_order=1, snippet="[image]"),
        "message": "No alt text.",
        "suggestion": "Add some.",
        "source": Source.RULE,
        "confidence": 1.0,
    }
    finding = Finding(**{**base, **finding_kw})
    return Report(
        generated_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
        meta=DocMeta(
            title="t",
            language="en-US",
            word_count=10,
            paragraph_count=2,
            image_count=1,
            table_count=0,
            sha256="ab" * 32,
        ),
        score=83,
        counts={Severity.CRITICAL: 1, Severity.HIGH: 0, Severity.MEDIUM: 0, Severity.LOW: 0},
        findings=[finding],
        llm=None,
        mode="rules_only",
        warnings=["A <b>note</b> & more"],
    )


def test_catalog_describes_every_rule() -> None:
    catalog = rule_catalog()
    assert len(catalog) == len(REGISTRY) + len(LLM_RULES) == 26
    assert [r.id for r in catalog] == sorted(r.id for r in catalog)
    assert all(r.description and r.how_to_fix for r in catalog)
    assert {r.source for r in catalog} == {"rule", "llm"}
    rule = get_rule(" img-001 ")
    assert rule is not None
    assert rule.wcag_url and rule.wcag_url.endswith("/non-text-content")
    assert get_rule("HDG-005") is not None
    assert get_rule("HDG-005").wcag_url is None  # type: ignore[union-attr]
    assert get_rule("NOPE-1") is None


def test_html_escapes_everything_from_the_document() -> None:
    payload = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    html = render_html(make_report(message=payload, suggestion=payload))
    assert "<script" not in html.lower()
    assert "&lt;script&gt;" in html
    assert "<img" not in html
    assert "&lt;b&gt;note&lt;/b&gt;" in html  # warnings are escaped too


def test_html_is_accessible_and_self_contained() -> None:
    html = render_html(make_report())
    assert '<html lang="en">' in html
    assert "<title>" in html
    assert html.count("<h1") == 1
    assert 'scope="col"' in html
    assert 'scope="row"' in html
    assert "<caption>" in html
    assert "<script" not in html
    assert "http://" not in html and "https://" not in html  # no external loads
    assert HTML_CSP == "default-src 'none'; style-src 'unsafe-inline'"
    assert "Score: 83 / 100" in html
    assert "never below 0" in html  # the score formula is documented in the footer


@pytest.mark.parametrize("value", HOSTILE)
def test_safe_cell_neutralises_formulas(value: str) -> None:
    safe = safe_cell(value)
    assert isinstance(safe, str)
    assert safe.startswith("'")


def test_safe_cell_leaves_other_values_alone() -> None:
    assert safe_cell("plain text") == "plain text"
    assert safe_cell(42) == 42
    assert safe_cell(0.5) == 0.5
    assert safe_cell("a\x00b") == "a b"


def test_xlsx_cells_never_become_formulas() -> None:
    report = make_report(message=HOSTILE[0], suggestion=HOSTILE[1])
    report.findings[0].location.snippet = HOSTILE[2]
    report.warnings.append(HOSTILE[3])
    workbook = load_workbook(io.BytesIO(render_xlsx(report)))
    assert workbook.sheetnames == ["Summary", "Findings"]
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                assert cell.data_type != "f", (sheet.title, cell.coordinate)
                if isinstance(cell.value, str):
                    assert not cell.value.startswith(("=", "+", "-", "@", "\t", "\r"))
    findings = workbook["Findings"]
    assert findings["H2"].value.startswith("'=HYPERLINK")
    assert findings["F2"].value == 1  # numbers stay numbers
    assert findings["A2"].value == "critical"


def test_xlsx_summary_has_score_and_counts() -> None:
    workbook = load_workbook(io.BytesIO(render_xlsx(make_report())))
    values = {r[0].value: r[1].value for r in workbook["Summary"].iter_rows()}
    assert values["Score (0-100)"] == 83
    assert values["Critical findings"] == 1
