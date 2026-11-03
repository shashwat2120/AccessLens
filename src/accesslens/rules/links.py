"""Link rules LNK-001 and LNK-002. LNK-003 needs context and lives in the LLM layer."""

import re

from accesslens.models import ParsedDocument, Severity, WcagLevel
from accesslens.rules.base import Hit, RuleConfig, blocks_by_id, rule

_VAGUE = {"click here", "here", "read more", "link", "more", "this"}
_URL = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)
_PUNCTUATION = re.compile(r"[^\w\s]")


@rule("LNK-001", "Non-descriptive link text", Severity.MEDIUM, "2.4.4", WcagLevel.A)
def vague_link_text(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    return [
        Hit(
            by_id[link.block_id],
            "The link text does not say where the link goes.",
            "Use text that describes the destination, such as the page or document name.",
        )
        for link in doc.links
        if _PUNCTUATION.sub("", link.text).strip().lower() in _VAGUE
    ]


@rule("LNK-002", "Raw URL used as link text", Severity.LOW, "2.4.4", WcagLevel.A)
def url_as_text(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    return [
        Hit(
            by_id[link.block_id],
            "A web address is used as the link text.",
            "Replace it with a short description of the destination.",
        )
        for link in doc.links
        if _URL.match(link.text.strip())
    ]
