"""HTML building blocks for the UI.

Everything that comes from a document or an API response is escaped here; nothing in this
module may put raw document text into markup. Links are restricted to https URLs on a short
allow-list.
"""

from html import escape
from typing import Any

from theme import SEVERITIES, SEVERITY_STYLE, score_band

WCAG_HOSTS = ("https://www.w3.org/",)
REPO_URL = "https://github.com/shashwat2120/AccessLens"
CATEGORIES = (
    ("Images and alt text", "Missing, placeholder or unhelpful descriptions"),
    ("Headings and structure", "Skipped levels, fake headings, empty headings"),
    ("Links", "Vague text such as 'click here', bare URLs"),
    ("Tables and lists", "Header rows, merged cells, hand-typed lists"),
    ("Colour contrast", "Text that is too faint to read comfortably"),
    ("Readability", "Reading level, very long sentences, jargon"),
    ("Slides (.pptx)", "Missing or repeated titles, reading order, tiny text, blank placeholders"),
)

LOGO_SVG = (
    '<svg width="34" height="34" viewBox="0 0 34 34" role="img" aria-label="AccessLens logo" '
    'xmlns="http://www.w3.org/2000/svg"><circle cx="15" cy="15" r="10" fill="none" '
    'stroke="#fff" stroke-width="3"/><path d="M23 23l8 8" stroke="#fff" stroke-width="3.4" '
    'stroke-linecap="round"/><path d="M10.5 15.5l3.2 3.2 6-6.6" fill="none" stroke="#fff" '
    'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


def e(value: Any) -> str:
    """Escape for HTML text and attributes."""
    return escape(str(value), quote=True)


def safe_url(url: str | None) -> str | None:
    return url if url and url.startswith(WCAG_HOSTS) else None


EXAMPLE_ROWS = (
    ("critical", "Image has no alt text"),
    ("high", "Table has no header row"),
    ("medium", "Skipped heading level"),
)


def example_preview_html() -> str:
    """A static, illustrative sample of a result for the hero; not data from any document."""
    rows = "".join(
        f'<div class="al-preview-row">{chip_html(severity)}<span>{e(text)}</span></div>'
        for severity, text in EXAMPLE_ROWS
    )
    return (
        '<div class="al-preview" aria-hidden="true">'
        '<div class="al-preview-label">Example result</div>'
        f'<div class="al-preview-score">{score_ring_html(72)}<div>'
        '<div class="al-preview-word">Good</div><div class="al-muted">5 issues found</div>'
        f"</div></div>{rows}</div>"
    )


def hero_html() -> str:
    return (
        '<section class="al-hero" aria-label="AccessLens"><div class="al-hero-copy">'
        f'<div class="al-brand">{LOGO_SVG}<span>AccessLens</span></div>'
        "<h1>Find and fix accessibility problems in Word and PowerPoint files</h1>"
        "<p>Upload a .docx or .pptx and get a prioritized, plain-language fix list, mapped to "
        "WCAG 2.2. "
        "Clear-cut checks are rule-based; AI helps only with judgement calls.</p>"
        '<div class="al-pills"><span class="al-pill">WCAG 2.2</span>'
        '<span class="al-pill">31 checks</span><span class="al-pill">Rules plus optional AI</span>'
        '<span class="al-pill">Nothing stored</span></div></div>'
        f"{example_preview_html()}</section>"
    )


def topbar_html() -> str:
    """Slim header shown once results are on screen (the large hero is for first-time visitors)."""
    return (
        f'<header class="al-topbar"><div class="al-brand">{LOGO_SVG}<span>AccessLens</span></div>'
        '<span class="al-topbar-tag">Word and PowerPoint accessibility checker, '
        "mapped to WCAG 2.2</span></header>"
    )


def checks_card_html() -> str:
    items = "".join(
        f'<li><span class="al-dot" aria-hidden="true"></span><div><b>{e(name)}</b>'
        f'<span class="al-muted">{e(detail)}</span></div></li>'
        for name, detail in CATEGORIES
    )
    return (
        '<div class="al-card"><div class="al-card-title">What AccessLens checks</div>'
        f'<ul class="al-checks">{items}</ul></div>'
    )


def privacy_html() -> str:
    return (
        '<div class="al-privacy"><strong>Your privacy.</strong> Documents are processed in '
        "memory and never stored. <b>Rules only</b> sends nothing to any AI service. "
        "<b>AI review</b> sends short text excerpts, and images that have alt text, to Google "
        "Gemini (with Groq as a fallback); free tiers may use them to improve their products, "
        "so do not use AI review on confidential documents.</div>"
    )


def chip_html(severity: str) -> str:
    label, fg, bg, border, _ = SEVERITY_STYLE[severity]
    return (
        f'<span class="al-chip" style="color:{fg};background:{bg};border-color:{border}">'
        f"{e(label)}</span>"
    )


def score_ring_html(score: int) -> str:
    word, colour = score_band(score)
    circumference = 2 * 3.14159 * 52
    filled = circumference * max(0, min(score, 100)) / 100
    ring = (
        f'<svg width="124" height="124" viewBox="0 0 124 124" role="img" '
        f'aria-label="Accessibility score {score} out of 100, {e(word)}">'
        '<circle cx="62" cy="62" r="52" fill="none" stroke="#E2E8F0" stroke-width="11"/>'
        f'<circle cx="62" cy="62" r="52" fill="none" stroke="{colour}" stroke-width="11" '
        f'stroke-linecap="round" stroke-dasharray="{filled:.1f} {circumference:.1f}" '
        'transform="rotate(-90 62 62)"/>'
        f'<text x="62" y="62" text-anchor="middle" font-size="34" font-weight="800" '
        f'fill="{colour}">{score}</text>'
        '<text x="62" y="84" text-anchor="middle" font-size="13" fill="#4B5563">'
        "out of 100</text></svg>"
    )
    return ring


def score_card_html(score: int, total: int, mode: str) -> str:
    word, colour = score_band(score)
    how = "Rules only" if mode == "rules_only" else "Rules plus AI review"
    plural = "" if total == 1 else "s"
    return (
        '<div class="al-card"><div class="al-score">'
        f"{score_ring_html(score)}<div>"
        f'<div class="al-word" style="color:{colour}">{e(word)}</div>'
        f'<div class="al-sub">{total} issue{plural} found</div>'
        f'<div class="al-sub">{e(how)}</div></div></div></div>'
    )


def stat_card_html(severity: str, count: int) -> str:
    label, fg, bg, border, _ = SEVERITY_STYLE[severity]
    return (
        f'<div class="al-stat" style="background:{bg};border-color:{border};color:{fg}">'
        f'<div class="al-n">{int(count)}</div><div class="al-l">{e(label)}</div></div>'
    )


def finding_html(finding: dict[str, Any], rule: dict[str, Any] | None = None) -> str:
    severity = finding["severity"] if finding["severity"] in SEVERITY_STYLE else "low"
    accent = SEVERITY_STYLE[severity][4]
    where = finding["location"]
    badges = []
    criterion = finding.get("wcag_criterion")
    if criterion:
        url = safe_url((rule or {}).get("wcag_url"))
        text = f"WCAG {e(criterion)}"
        badges.append(
            f'<a class="al-badge" href="{e(url)}" target="_blank" '
            f'rel="noopener noreferrer">{text}</a>'
            if url
            else f'<span class="al-badge">{text}</span>'
        )
    if finding.get("source") == "llm":
        badges.append(
            f'<span class="al-badge">AI review, {round(finding["confidence"] * 100)}% sure</span>'
        )
    return (
        f'<article class="al-finding" style="border-left-color:{accent}">'
        f'<header>{chip_html(severity)}<span class="al-rule">{e(finding["rule_id"])}</span>'
        f"<strong>{e(finding['title'])}</strong>{''.join(badges)}</header>"
        f'<p class="al-where">{_place(where)}: '
        f"<code>{e(where['snippet'])}</code></p>"
        f'<p class="al-problem">{e(finding["message"])}</p>'
        f'<div class="al-fix"><strong>How to fix</strong>{e(finding["suggestion"])}</div></article>'
    )


def _place(where: dict[str, Any]) -> str:
    slide = where.get("slide")
    return f"Slide {int(slide)}" if slide else f"Block {int(where['block_order'])}"


def group_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group findings by rule, most severe and largest groups first."""
    rank = {name: i for i, name in enumerate(SEVERITIES)}
    groups: dict[str, dict[str, Any]] = {}
    for finding in findings:
        group = groups.setdefault(
            finding["rule_id"],
            {
                "rule_id": finding["rule_id"],
                "title": finding["title"],
                "severity": finding["severity"],
                "items": [],
            },
        )
        group["items"].append(finding)
    return sorted(
        groups.values(),
        key=lambda g: (rank.get(g["severity"], 9), -len(g["items"]), g["rule_id"]),
    )


def footer_html() -> str:
    return (
        '<div class="al-footer">AccessLens is open source (MIT), by Shashwat Mishra. '
        "It checks common problems and is not a complete accessibility audit; "
        "test important documents with assistive technology. "
        f'<a href="{REPO_URL}" target="_blank" rel="noopener noreferrer">'
        "Source and documentation</a>.</div>"
    )
