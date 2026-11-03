"""Document property rules DOC-001 and DOC-002."""

from accesslens.models import ParsedDocument, Severity, WcagLevel
from accesslens.rules.base import Hit, RuleConfig, first_block, rule


@rule("DOC-001", "Document title is empty", Severity.MEDIUM, "2.4.2", WcagLevel.A)
def missing_title(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    if (doc.meta.title or "").strip():
        return []
    return [
        Hit(
            first_block(doc),
            "The document title property is empty.",
            "Set a descriptive title under File > Info > Properties.",
        )
    ]


@rule("DOC-002", "Document language is not set", Severity.MEDIUM, "3.1.1", WcagLevel.A)
def missing_language(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    if (doc.meta.language or "").strip():
        return []
    return [
        Hit(
            first_block(doc),
            "The default document language is not set.",
            "Set the proofing language so screen readers pronounce the text correctly.",
        )
    ]
