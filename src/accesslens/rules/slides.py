"""Slide rules SLD-001 to SLD-005. They run on .pptx only (see ``base.kinds_for``)."""

from collections import defaultdict

from accesslens.models import ParsedDocument, Severity, WcagLevel
from accesslens.rules.base import Hit, RuleConfig, blocks_by_id, rule

_BODY = ("paragraph", "list_item")


@rule("SLD-001", "Slide has no title", Severity.HIGH, "2.4.2", WcagLevel.A)
def missing_title(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    return [
        Hit(
            by_id[s.block_id],
            f"Slide {s.number} has no title, so screen reader users cannot tell slides apart "
            "or jump between them.",
            "Add a title to the slide. If it should not show, keep the title placeholder "
            "and move it off the slide.",
        )
        for s in doc.slides
        if not s.title.strip()
    ]


@rule("SLD-002", "Two slides share a title", Severity.LOW, "2.4.6", WcagLevel.AA)
def duplicate_title(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    seen: dict[str, list[int]] = defaultdict(list)
    for slide in doc.slides:
        key = " ".join(slide.title.lower().split())
        if key:
            seen[key].append(slide.number)
    hits: list[Hit] = []
    for slide in doc.slides:
        key = " ".join(slide.title.lower().split())
        numbers = seen.get(key, [])
        if key and len(numbers) > 1 and slide.number != numbers[0]:
            hits.append(
                Hit(
                    by_id[slide.block_id],
                    f"Slide {slide.number} has the same title as slide {numbers[0]}.",
                    "Give each slide a title that says what is different about it, "
                    "for example 'Results (continued)'.",
                )
            )
    return hits


@rule("SLD-003", "Title is not first in reading order", Severity.MEDIUM, "1.3.2", WcagLevel.A)
def title_not_first(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    return [
        Hit(
            by_id[s.block_id],
            f"On slide {s.number} a screen reader reads other content before the title.",
            "Open Home > Arrange > Selection Pane (Reading Order Pane) and move the title "
            "to the bottom of the list, which is read first.",
        )
        for s in doc.slides
        if s.has_title_placeholder and s.title.strip() and not s.title_is_first
    ]


@rule("SLD-004", "Slide text is too small", Severity.LOW, None, WcagLevel.BEST_PRACTICE)
def small_slide_text(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    return [
        Hit(
            block,
            f"Text on slide {block.slide} is smaller than {config.min_slide_pt:g} pt, "
            "which is hard to read when projected.",
            "Use at least 18 pt for body text on slides, and never below "
            f"{config.min_slide_pt:g} pt.",
        )
        for block in doc.blocks
        if block.type in _BODY
        and any(
            r.text.strip() and r.size_pt is not None and r.size_pt < config.min_slide_pt
            for r in block.runs
        )
    ]


@rule("SLD-005", "Slide has an empty placeholder", Severity.LOW, "1.3.1", WcagLevel.A)
def empty_placeholder(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    return [
        Hit(
            by_id[s.block_id],
            f"Slide {s.number} has {s.empty_placeholders} empty placeholder"
            f"{'s' if s.empty_placeholders != 1 else ''}, which screen readers announce "
            "as blank content.",
            "Add content to the placeholder or delete it.",
        )
        for s in doc.slides
        if s.empty_placeholders
    ]
