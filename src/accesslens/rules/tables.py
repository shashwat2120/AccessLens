"""Table rules TBL-001 to TBL-003."""

from accesslens.models import ParsedDocument, Severity, WcagLevel
from accesslens.rules.base import Hit, RuleConfig, blocks_by_id, rule


@rule("TBL-001", "Data table has no header row", Severity.HIGH, "1.3.1", WcagLevel.A)
def missing_header_row(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    return [
        Hit(
            by_id[t.block_id],
            "The first row is not marked as a header row.",
            "Select the first row and turn on 'Repeat as header row at the top of each page'.",
        )
        for t in doc.tables
        if t.rows >= 2 and t.cols >= 2 and not t.has_header_row
    ]


@rule("TBL-002", "Table has merged or split cells", Severity.MEDIUM, "1.3.1", WcagLevel.A)
def merged_cells(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    return [
        Hit(
            by_id[t.block_id],
            "The table has merged or split cells, which assistive technology reads poorly.",
            "Use a simple grid, or split the content into separate tables.",
        )
        for t in doc.tables
        if t.has_merged_cells
    ]


@rule("TBL-003", "Table is mostly empty", Severity.LOW, "1.3.1", WcagLevel.A)
def mostly_empty(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    by_id = blocks_by_id(doc)
    return [
        Hit(
            by_id[t.block_id],
            "Most cells are empty, so the table may be used for layout.",
            "Use paragraphs, columns or styles for layout instead of a table.",
        )
        for t in doc.tables
        if t.empty_cell_ratio > config.empty_table_ratio
    ]
