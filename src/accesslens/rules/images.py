"""Image rules IMG-001, 002, 004, 005. IMG-003 needs vision and lives in the LLM layer."""

import re

from accesslens.models import ParsedDocument, Severity, WcagLevel
from accesslens.rules.base import Hit, RuleConfig, blocks_by_id, rule

_PLACEHOLDERS = {"image", "picture", "graphic", "photo", "screenshot"}
_FILENAME = re.compile(r"\.(png|jpe?g|gif|bmp|tiff?|webp|svg|emf|wmf)$", re.IGNORECASE)


def _alt(image_alt: str | None) -> str:
    return (image_alt or "").strip()


@rule("IMG-001", "Image has no alt text", Severity.CRITICAL, "1.1.1", WcagLevel.A)
def missing_alt(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    return [
        Hit(
            by_id[i.block_id],
            "This image has no alternative text and is not marked decorative.",
            "Add a short description of what the image shows, or mark it decorative.",
        )
        for i in doc.images
        if not i.decorative and not _alt(i.alt_text)
    ]


@rule("IMG-002", "Alt text is a placeholder", Severity.HIGH, "1.1.1", WcagLevel.A)
def placeholder_alt(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    hits: list[Hit] = []
    for image in doc.images:
        alt = _alt(image.alt_text)
        if image.decorative or not alt:
            continue
        if alt.lower() in _PLACEHOLDERS or _FILENAME.search(alt) or len(alt) < config.alt_min_chars:
            hits.append(
                Hit(
                    by_id[image.block_id],
                    "The alt text is a placeholder or file name, not a description.",
                    "Replace it with a short description of what the image shows and why.",
                )
            )
    return hits


@rule("IMG-004", "Alt text is too long", Severity.LOW, "1.1.1", WcagLevel.A)
def long_alt(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    return [
        Hit(
            by_id[i.block_id],
            f"The alt text is over {config.alt_max_chars} characters.",
            "Shorten the alt text and move the detail into a caption or the body text.",
        )
        for i in doc.images
        if not i.decorative and len(_alt(i.alt_text)) > config.alt_max_chars
    ]


@rule("IMG-005", "Floating image may break reading order", Severity.MEDIUM, "1.3.2", WcagLevel.A)
def floating_image(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    return [
        Hit(
            by_id[i.block_id],
            "This image floats instead of sitting in the text line.",
            "Set the wrapping to 'In line with text' so screen readers meet it in order.",
        )
        for i in doc.images
        if not i.inline
    ]
