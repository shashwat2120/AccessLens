from pathlib import Path
from typing import Any

import pytest
from components import (
    finding_html,
    group_findings,
    hero_html,
    safe_url,
    score_card_html,
    score_ring_html,
    stat_card_html,
)
from theme import CONTRAST_PAIRS, CSS, SEVERITIES, SEVERITY_STYLE, score_band

from accesslens.ingest.parse_docx import parse_docx
from accesslens.ingest.parse_pptx import parse_pptx
from accesslens.report.score import compute_score
from accesslens.rules import run_rules
from accesslens.rules.catalog import rule_catalog
from accesslens.rules.color import contrast_ratio

ROOT = Path(__file__).resolve().parents[2]
HOSTILE = '<script>alert(1)</script><img src=x onerror="alert(2)"> & "quote"'


def finding(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "rule_id": "IMG-001",
        "title": "Image has no alt text",
        "severity": "critical",
        "wcag_criterion": "1.1.1",
        "location": {"block_order": 3, "snippet": "[image]"},
        "message": "No alt text.",
        "suggestion": "Add some.",
        "source": "rule",
        "confidence": 1.0,
    }
    return {**base, **kw}


@pytest.mark.parametrize("name,fg,bg", CONTRAST_PAIRS, ids=[p[0] for p in CONTRAST_PAIRS])
def test_every_colour_pair_reaches_wcag_aa(name: str, fg: str, bg: str) -> None:
    """The UI is held to the same rule AccessLens enforces on documents (CLR-001)."""
    assert contrast_ratio(fg.lstrip("#"), bg.lstrip("#")) >= 4.5, name


def test_document_text_cannot_inject_markup() -> None:
    html = finding_html(
        finding(
            title=HOSTILE,
            message=HOSTILE,
            suggestion=HOSTILE,
            rule_id=HOSTILE,
            location={"block_order": 1, "snippet": HOSTILE},
        )
    )
    assert "<script" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert 'onerror="' not in html  # quotes are escaped, so no attribute can be opened


def test_unknown_severity_falls_back_and_numbers_are_coerced() -> None:
    html = finding_html(
        finding(severity="<b>bad</b>", location={"block_order": "7", "snippet": "x"})
    )
    assert "<b>bad</b>" not in html
    assert "Block 7" in html
    assert "Low" in html


def test_only_wcag_links_on_the_allow_list_are_followed() -> None:
    good = "https://www.w3.org/WAI/WCAG22/Understanding/non-text-content"
    assert safe_url(good) == good
    for bad in ("javascript:alert(1)", "http://www.w3.org/x", "https://evil.example/", None, ""):
        assert safe_url(bad) is None
    linked = finding_html(finding(), {"wcag_url": good})
    assert f'href="{good}"' in linked
    assert 'rel="noopener noreferrer"' in linked
    unlinked = finding_html(finding(), {"wcag_url": "javascript:alert(1)"})
    assert "javascript:" not in unlinked
    assert 'class="al-badge">WCAG 1.1.1' in unlinked


def test_ai_findings_are_labelled_with_their_confidence() -> None:
    assert "AI review, 85% sure" in finding_html(finding(source="llm", confidence=0.85))
    assert "AI review" not in finding_html(finding())


def test_score_bands_and_ring() -> None:
    assert [score_band(s)[0] for s in (100, 90, 89, 70, 69, 40, 39, 0)] == [
        "Excellent",
        "Excellent",
        "Good",
        "Good",
        "Needs work",
        "Needs work",
        "Poor",
        "Poor",
    ]
    ring = score_ring_html(55)
    assert 'role="img"' in ring
    assert "Accessibility score 55 out of 100, Needs work" in ring
    assert "NaN" not in score_ring_html(-20) + score_ring_html(250)  # out-of-range is clamped


def test_cards_show_the_numbers_and_words_not_just_colour() -> None:
    card = score_card_html(55, 8, "rules_only")
    assert "Needs work" in card and "8 issues found" in card and "Rules only" in card
    assert "1 issue found" in score_card_html(90, 1, "full")
    assert "Rules plus AI review" in score_card_html(90, 1, "full")
    stat = stat_card_html("high", 2)
    assert ">2<" in stat and "High" in stat


def test_findings_group_by_rule_most_severe_and_largest_first() -> None:
    groups = group_findings(
        [
            finding(rule_id="TXT-002", severity="low"),
            finding(rule_id="TXT-002", severity="low"),
            finding(rule_id="TXT-003", severity="low"),
            finding(rule_id="TBL-001", severity="high"),
            finding(rule_id="IMG-001", severity="critical"),
        ]
    )
    assert [(g["rule_id"], len(g["items"])) for g in groups] == [
        ("IMG-001", 1),
        ("TBL-001", 1),
        ("TXT-002", 2),
        ("TXT-003", 1),
    ]


def test_every_severity_has_a_style_and_the_stylesheet_is_balanced() -> None:
    assert set(SEVERITIES) == set(SEVERITY_STYLE)
    css = CSS.replace("{{", "{").replace("}}", "}")  # the template doubles its braces
    assert css.count("{") == css.count("}")


def test_slide_findings_say_which_slide() -> None:
    on_slide = finding_html(finding(location={"block_order": 9, "snippet": "x", "slide": 4}))
    assert "Slide 4" in on_slide and "Block 9" not in on_slide
    assert "Block 3" in finding_html(finding())  # Word findings keep the block number


def test_the_hero_claims_the_real_number_of_checks() -> None:
    assert f"{len(rule_catalog())} checks" in hero_html()


def test_the_bundled_sample_deck_shows_every_severity() -> None:
    sample = ROOT / "ui" / "samples" / "sample-team-update.pptx"
    findings, warnings = run_rules(parse_pptx(sample.read_bytes()))
    assert not warnings
    assert {f.severity.value for f in findings} == set(SEVERITIES)


def test_the_bundled_sample_shows_every_severity() -> None:
    sample = ROOT / "ui" / "samples" / "sample-quarterly-report.docx"
    findings, warnings = run_rules(parse_docx(sample.read_bytes()))
    assert not warnings
    assert {f.severity.value for f in findings} == set(SEVERITIES)
    assert 0 < compute_score(findings) < 90
