"""Text and readability rules TXT-001 to TXT-005. TXT-006 needs judgement (LLM layer)."""

import re

import textstat

from accesslens.models import ParsedDocument, Severity, WcagLevel
from accesslens.rules.base import Hit, RuleConfig, rule, sections

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_EDGE_PUNCTUATION = ".,;:!?\"'()[]"
_BODY = ("paragraph", "list_item")


def _terminated(text: str) -> str:
    """Make list items and fragments count as sentences for readability scoring."""
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


@rule(
    "TXT-001",
    "Reading level is above the target grade",
    Severity.MEDIUM,
    "3.1.5",
    WcagLevel.AAA,
)
def reading_grade(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    hits: list[Hit] = []
    for blocks in sections(doc):
        text = " ".join(_terminated(b.text) for b in blocks)
        if len(text.split()) < config.min_words_for_grade:
            continue  # too short for a stable score
        grade = float(textstat.flesch_kincaid_grade(text))
        if grade > config.target_grade:
            hits.append(
                Hit(
                    blocks[0],
                    f"This section reads at about grade {grade:.0f}; the target is "
                    f"grade {config.target_grade}.",
                    "Use shorter sentences and everyday words.",
                )
            )
    return hits


@rule("TXT-002", "Sentence is too long", Severity.LOW, "3.1.5", WcagLevel.AAA)
def long_sentence(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    hits: list[Hit] = []
    for block in doc.blocks:
        if block.type not in _BODY:
            continue
        for sentence in _SENTENCE_END.split(block.text):
            count = len(sentence.split())
            if count > config.long_sentence_words:
                hits.append(
                    Hit(
                        block,
                        f"A sentence has {count} words; the limit is {config.long_sentence_words}.",
                        "Split it into two or more shorter sentences.",
                    )
                )
                break  # one finding per block
    return hits


@rule("TXT-003", "Long run of capital letters", Severity.LOW, None, WcagLevel.BEST_PRACTICE)
def all_caps_run(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    hits: list[Hit] = []
    for block in doc.blocks:
        streak = 0
        for token in block.text.split():
            word = token.strip(_EDGE_PUNCTUATION)
            streak = streak + 1 if len(word) >= 2 and word.isalpha() and word.isupper() else 0
            if streak > config.caps_run_words:
                hits.append(
                    Hit(
                        block,
                        "A run of words is written in all capitals.",
                        "Use sentence case; capitals are harder to read and some tools "
                        "spell them out.",
                    )
                )
                break
    return hits


@rule("TXT-004", "Underlined text that is not a link", Severity.LOW, None, WcagLevel.BEST_PRACTICE)
def underlined_text(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    return [
        Hit(
            block,
            "Text is underlined but is not a link.",
            "Remove the underline, or use bold or italic for emphasis.",
        )
        for block in doc.blocks
        if any(r.underline and r.hyperlink_url is None and r.text.strip() for r in block.runs)
    ]


@rule("TXT-005", "Body text is too small", Severity.LOW, None, WcagLevel.BEST_PRACTICE)
def small_text(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    return [
        Hit(
            block,
            f"Body text is smaller than {config.min_body_pt:g} pt.",
            "Increase the font size to at least 11 pt for body text.",
        )
        for block in doc.blocks
        if block.type in _BODY
        and any(
            r.text.strip() and r.size_pt is not None and r.size_pt < config.min_body_pt
            for r in block.runs
        )
    ]
