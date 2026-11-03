"""List rule LST-001."""

import re

from accesslens.models import Block, ParsedDocument, Severity, WcagLevel
from accesslens.rules.base import Hit, RuleConfig, rule

# Typed markers: - * bullet, en/em dash, middle dot, "1." "2)" "a." "b)". Built from code
# points so the source stays ASCII and linters cannot flag the look-alike dashes.
_BULLETS = re.escape("-*" + "".join(chr(code) for code in (0x2022, 0x2013, 0x2014, 0x00B7)))
_MARKER = re.compile(rf"^\s*([{_BULLETS}]|\d+[.)]|[a-zA-Z][.)])\s+\S")


@rule("LST-001", "List typed by hand", Severity.LOW, "1.3.1", WcagLevel.A)
def fake_list(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    hits: list[Hit] = []
    run: list[Block] = []

    def flush() -> None:
        if len(run) >= config.fake_list_min_items:
            hits.append(
                Hit(
                    run[0],
                    "Consecutive paragraphs start with typed list markers.",
                    "Use the Bullets or Numbering buttons to create a real list.",
                )
            )
        run.clear()

    for block in doc.blocks:
        if block.type == "paragraph" and _MARKER.match(block.text):
            run.append(block)
        else:
            flush()
    flush()
    return hits
