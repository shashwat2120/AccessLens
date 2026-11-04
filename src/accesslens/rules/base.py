"""Rule registry and finding construction (TRD §4, docs/04-RULES-CATALOG.md).

A rule's check is a pure function ``(ParsedDocument, RuleConfig) -> list[Hit]``. ``Rule.run``
turns hits into ``Finding`` objects, so ids, snippets and metadata are built in one place.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from accesslens.models import (
    Block,
    Finding,
    Location,
    ParsedDocument,
    Severity,
    Source,
    WcagLevel,
)

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_SNIPPET = 120  # models.Location enforces the same cap


class RuleConfig(BaseModel):
    """Every threshold a rule uses; nothing numeric is hard-coded inside a rule."""

    target_grade: int = 9
    min_words_for_grade: int = 30
    long_sentence_words: int = 30
    caps_run_words: int = 3  # flag runs of MORE than this many all-caps words
    alt_min_chars: int = 4  # alt text shorter than this is a placeholder
    alt_max_chars: int = 250
    long_doc_words: int = 300
    fake_heading_max_words: int = 12
    fake_heading_min_pt: float = 14.0
    fake_list_min_items: int = 2
    empty_table_ratio: float = 0.5
    min_body_pt: float = 10.0
    min_slide_pt: float = 12.0
    default_text_pt: float = 11.0
    contrast_normal: float = 4.5
    contrast_large: float = 3.0
    large_text_pt: float = 18.0
    large_bold_pt: float = 14.0


@dataclass(frozen=True)
class Hit:
    """One place a rule fired, before it becomes a ``Finding``."""

    block: Block
    message: str
    suggestion: str


CheckFn = Callable[[ParsedDocument, RuleConfig], list[Hit]]


def snippet_of(block: Block) -> str:
    text = _CONTROL_CHARS.sub(" ", block.text).strip()
    return (text or f"[{block.type}]")[:_MAX_SNIPPET]


# Rules that only make sense for Word documents: they rely on heading styles, floating images,
# typed lists or a white page, none of which a slide has. Rules with the SLD- prefix are
# slide-only. Every other rule applies to both formats.
_DOCX_ONLY = frozenset(
    {
        "IMG-005",
        "HDG-001",
        "HDG-002",
        "HDG-003",
        "HDG-004",
        "HDG-005",
        "LST-001",
        "CLR-001",  # needs the page background, which a themed slide does not state
        "TXT-001",
        "TXT-005",  # slides have their own, larger, size rule (SLD-004)
    }
)
ALL_KINDS = frozenset({"docx", "pptx"})


def kinds_for(rule_id: str) -> frozenset[str]:
    if rule_id.startswith("SLD-"):
        return frozenset({"pptx"})
    return frozenset({"docx"}) if rule_id in _DOCX_ONLY else ALL_KINDS


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: Severity
    wcag_criterion: str | None
    wcag_level: WcagLevel
    confidence: float
    check: CheckFn

    @property
    def kinds(self) -> frozenset[str]:
        return kinds_for(self.id)

    def run(self, doc: ParsedDocument, config: RuleConfig) -> list[Finding]:
        """Run the check and return findings; ids are unique per rule and block."""
        findings: list[Finding] = []
        seen: dict[str, int] = {}
        for hit in self.check(doc, config):
            base = f"{self.id}-{hit.block.id}"
            n = seen.get(base, 0)
            seen[base] = n + 1
            findings.append(
                Finding(
                    id=base if n == 0 else f"{base}-{n}",
                    rule_id=self.id,
                    title=self.title,
                    severity=self.severity,
                    wcag_criterion=self.wcag_criterion,
                    wcag_level=self.wcag_level,
                    location=Location(
                        block_id=hit.block.id,
                        block_order=hit.block.order,
                        snippet=snippet_of(hit.block),
                        slide=hit.block.slide,
                    ),
                    message=hit.message,
                    suggestion=hit.suggestion,
                    source=Source.RULE,
                    confidence=self.confidence,
                )
            )
        return findings


REGISTRY: dict[str, Rule] = {}


def rule(
    rule_id: str,
    title: str,
    severity: Severity,
    wcag_criterion: str | None,
    wcag_level: WcagLevel,
    *,
    confidence: float = 1.0,
) -> Callable[[CheckFn], CheckFn]:
    """Register a check under a catalog rule id. Ids are never reused."""

    def decorate(fn: CheckFn) -> CheckFn:
        if rule_id in REGISTRY:
            raise ValueError(f"duplicate rule id {rule_id}")
        REGISTRY[rule_id] = Rule(
            rule_id, title, severity, wcag_criterion, wcag_level, confidence, fn
        )
        return fn

    return decorate


def blocks_by_id(doc: ParsedDocument) -> dict[str, Block]:
    return {b.id: b for b in doc.blocks}


def first_block(doc: ParsedDocument) -> Block:
    """Anchor for document-level findings; a placeholder if the document has no blocks."""
    if doc.blocks:
        return doc.blocks[0]
    return Block(id="b0000", order=0, type="paragraph", text="")


def sections(doc: ParsedDocument) -> list[list[Block]]:
    """Text blocks grouped under each heading (text before the first heading is a section)."""
    groups: list[list[Block]] = [[]]
    for block in doc.blocks:
        if block.type in ("heading", "title"):
            groups.append([])
        elif block.type in ("paragraph", "list_item") and block.text.strip():
            groups[-1].append(block)
    return [g for g in groups if g]
