"""Heading rules HDG-001 to HDG-005."""

from accesslens.models import Block, ParsedDocument, Severity, WcagLevel
from accesslens.rules.base import Hit, RuleConfig, first_block, rule


def _headings(doc: ParsedDocument) -> list[Block]:
    return [b for b in doc.blocks if b.type == "heading" and b.heading_level]


@rule("HDG-001", "Long document has no headings", Severity.HIGH, "1.3.1", WcagLevel.A)
def no_headings(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    if doc.meta.word_count > config.long_doc_words and not _headings(doc):
        return [
            Hit(
                first_block(doc),
                f"The document has over {config.long_doc_words} words and no heading styles.",
                "Apply Heading 1, Heading 2 and so on to section titles.",
            )
        ]
    return []


@rule("HDG-002", "Skipped heading level", Severity.MEDIUM, "1.3.1", WcagLevel.A)
def skipped_level(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    hits: list[Hit] = []
    previous: int | None = None
    for block in _headings(doc):
        level = block.heading_level or 1
        if previous is not None and level > previous + 1:
            hits.append(
                Hit(
                    block,
                    f"Heading level jumps from {previous} to {level}.",
                    f"Use Heading {previous + 1} here, or restructure the sections.",
                )
            )
        previous = level
    return hits


@rule(
    "HDG-003",
    "Text formatted like a heading but not a heading",
    Severity.MEDIUM,
    "1.3.1",
    WcagLevel.A,
    confidence=0.8,
)
def fake_heading(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    hits: list[Hit] = []
    for block, following in zip(doc.blocks, doc.blocks[1:], strict=False):
        if block.type != "paragraph" or not block.text.strip():
            continue
        if len(block.text.split()) > config.fake_heading_max_words:
            continue
        runs = [r for r in block.runs if r.text.strip()]
        looks_bold = bool(runs) and all(r.bold for r in runs)
        looks_big = any((r.size_pt or 0) >= config.fake_heading_min_pt for r in runs)
        followed_by_body = following.type in ("paragraph", "list_item") and bool(
            following.text.strip()
        )
        if (looks_bold or looks_big) and followed_by_body:
            hits.append(
                Hit(
                    block,
                    "This short bold or large paragraph looks like a heading.",
                    "Apply a real heading style instead of manual formatting.",
                )
            )
    return hits


@rule("HDG-004", "Empty heading", Severity.LOW, "2.4.6", WcagLevel.AA)
def empty_heading(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    return [
        Hit(b, "This heading has no text.", "Add text to the heading or remove it.")
        for b in _headings(doc)
        if not b.text.strip()
    ]


@rule(
    "HDG-005",
    "Document does not start with a single H1",
    Severity.LOW,
    None,
    WcagLevel.BEST_PRACTICE,
)
def title_structure(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    hits: list[Hit] = []
    first = next((b for b in doc.blocks if b.text.strip() or b.type in ("image", "table")), None)
    if first is not None and not (
        first.type == "title" or (first.type == "heading" and first.heading_level == 1)
    ):
        hits.append(
            Hit(
                first,
                "The document does not start with a Title or Heading 1.",
                "Begin the document with its title styled as Title or Heading 1.",
            )
        )
    h1s = [b for b in _headings(doc) if b.heading_level == 1]
    hits += [
        Hit(
            b,
            "The document has more than one Heading 1.",
            "Use Heading 1 once for the title and Heading 2 for main sections.",
        )
        for b in h1s[1:]
    ]
    return hits
