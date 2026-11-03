"""Public rule catalog: what every check is and how to fix it (API, MCP, reports).

Built from the registered rules plus the LLM-reviewed rules, so it cannot drift from the code;
a test fails if any rule lacks a description or fix.
"""

from dataclasses import dataclass
from typing import Literal

from accesslens.llm.checks import LLM_RULES
from accesslens.models import Severity, WcagLevel
from accesslens.rules import REGISTRY

_WCAG_BASE = "https://www.w3.org/WAI/WCAG22/Understanding/"
_WCAG_SLUGS = {
    "1.1.1": "non-text-content",
    "1.3.1": "info-and-relationships",
    "1.3.2": "meaningful-sequence",
    "1.4.3": "contrast-minimum",
    "2.4.2": "page-titled",
    "2.4.4": "link-purpose-in-context",
    "2.4.6": "headings-and-labels",
    "3.1.1": "language-of-page",
    "3.1.3": "unusual-words",
    "3.1.5": "reading-level",
}

# rule id -> (what it checks, how to fix it)
_GUIDANCE: dict[str, tuple[str, str]] = {
    "IMG-001": (
        "An image has no alternative text and is not marked decorative.",
        "Right-click the image, choose View Alt Text and describe what it shows, "
        "or mark it decorative.",
    ),
    "IMG-002": (
        "The alt text is a placeholder such as 'image', a file name, or under 4 characters.",
        "Replace it with a short description of what the image shows and why it is there.",
    ),
    "IMG-003": (
        "The alt text exists but does not describe the image's content or purpose (AI review).",
        "Rewrite the alt text to say what the image shows and what a reader needs from it.",
    ),
    "IMG-004": (
        "The alt text is over 250 characters.",
        "Shorten the alt text and put the detail in a caption or the body text.",
    ),
    "IMG-005": (
        "The image floats instead of sitting in the text line, which can break reading order.",
        "Set the image wrapping to 'In line with text'.",
    ),
    "HDG-001": (
        "A document of over 300 words has no heading styles.",
        "Style section titles with Heading 1, Heading 2 and so on.",
    ),
    "HDG-002": (
        "A heading level is skipped, for example Heading 1 followed by Heading 3.",
        "Use the next level down, or restructure the sections.",
    ),
    "HDG-003": (
        "Short bold or large text looks like a heading but has no heading style.",
        "Apply a real heading style instead of manual formatting.",
    ),
    "HDG-004": ("A heading has no text.", "Add text to the heading or delete it."),
    "HDG-005": (
        "The document does not start with a Title or Heading 1, or has more than one Heading 1.",
        "Start with the title as Title or Heading 1 and use Heading 2 for main sections.",
    ),
    "DOC-001": (
        "The document title property is empty.",
        "Set the title under File > Info > Properties.",
    ),
    "DOC-002": (
        "The default document language is not set.",
        "Set the proofing language so screen readers pronounce the text correctly.",
    ),
    "LNK-001": (
        "Link text such as 'click here' or 'read more' does not describe the destination.",
        "Make the link text describe where it goes.",
    ),
    "LNK-002": (
        "A raw web address is used as link text.",
        "Replace it with a short description of the destination.",
    ),
    "LNK-003": (
        "The link text is unclear even in context (AI review).",
        "Rewrite the link text so its purpose is clear from the text and its sentence.",
    ),
    "TBL-001": (
        "A data table has no header row.",
        "Select the first row and turn on 'Repeat as header row at the top of each page'.",
    ),
    "TBL-002": (
        "A table has merged or split cells.",
        "Use a simple grid, or split the content into separate tables.",
    ),
    "TBL-003": (
        "More than half of a table's cells are empty, so it may be used for layout.",
        "Use paragraphs, columns or styles for layout instead of a table.",
    ),
    "LST-001": (
        "Consecutive paragraphs start with typed list markers.",
        "Use the Bullets or Numbering buttons to make a real list.",
    ),
    "CLR-001": (
        "Text colour contrast is below 4.5:1 (3:1 for large text).",
        "Use a darker text colour or a lighter background.",
    ),
    "TXT-001": (
        "A section reads above the target grade level.",
        "Use shorter sentences and everyday words.",
    ),
    "TXT-002": ("A sentence is over 30 words.", "Split it into shorter sentences."),
    "TXT-003": (
        "A run of more than three words is in all capitals.",
        "Use sentence case.",
    ),
    "TXT-004": (
        "Text is underlined but is not a link.",
        "Remove the underline; use bold or italic for emphasis.",
    ),
    "TXT-005": (
        "Body text is smaller than 10 pt.",
        "Increase body text to at least 11 pt.",
    ),
    "TXT-006": (
        "Jargon or an abbreviation is used without explanation (AI review).",
        "Spell out abbreviations on first use or add a short definition.",
    ),
}


@dataclass(frozen=True)
class RuleInfo:
    id: str
    title: str
    severity: Severity
    wcag_criterion: str | None
    wcag_level: WcagLevel
    source: Literal["rule", "llm"]
    description: str
    how_to_fix: str
    wcag_url: str | None


def _url(criterion: str | None) -> str | None:
    slug = _WCAG_SLUGS.get(criterion or "")
    return f"{_WCAG_BASE}{slug}" if slug else None


def rule_catalog() -> list[RuleInfo]:
    """Every rule, rule-based and LLM-reviewed, sorted by id."""
    entries: list[RuleInfo] = []
    for rule in REGISTRY.values():
        description, fix = _GUIDANCE[rule.id]
        entries.append(
            RuleInfo(
                rule.id,
                rule.title,
                rule.severity,
                rule.wcag_criterion,
                rule.wcag_level,
                "rule",
                description,
                fix,
                _url(rule.wcag_criterion),
            )
        )
    for rule_id, (title, severity, criterion, level, _) in LLM_RULES.items():
        description, fix = _GUIDANCE[rule_id]
        entries.append(
            RuleInfo(
                rule_id, title, severity, criterion, level, "llm", description, fix, _url(criterion)
            )
        )
    return sorted(entries, key=lambda r: r.id)


def get_rule(rule_id: str) -> RuleInfo | None:
    return next((r for r in rule_catalog() if r.id == rule_id.strip().upper()), None)
