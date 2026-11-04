"""Data model shared by every layer (TRD §3)."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WcagLevel(StrEnum):
    A = "A"
    AA = "AA"
    AAA = "AAA"
    BEST_PRACTICE = "best_practice"


class Source(StrEnum):
    RULE = "rule"
    LLM = "llm"


class DocMeta(BaseModel):
    """Document facts. Author and last-modified-by are deliberately not stored (PII)."""

    title: str | None
    language: str | None
    word_count: int
    paragraph_count: int
    image_count: int
    table_count: int
    sha256: str  # of the uploaded file; never the filename
    kind: Literal["docx", "pptx"] = "docx"


class Run(BaseModel):
    """A formatted span inside a paragraph."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    size_pt: float | None = None
    color_hex: str | None = None
    highlight: str | None = None
    hyperlink_url: str | None = None  # set if the run is inside a hyperlink


class Block(BaseModel):
    id: str  # "b0042": stable, order-based
    order: int
    type: Literal["heading", "paragraph", "list_item", "table", "image", "title"]
    text: str
    style_name: str | None = None
    heading_level: int | None = None  # 1-9 for real heading styles
    runs: list[Run] = Field(default_factory=list)
    slide: int | None = None  # 1-based slide number; set for .pptx only


class SlideInfo(BaseModel):
    """Facts about one slide (.pptx). ``block_id`` is its title block, which always exists."""

    number: int
    block_id: str
    title: str
    has_title_placeholder: bool
    title_is_first: bool  # the title is the first shape in reading order
    empty_placeholders: int


class ImageInfo(BaseModel):
    id: str
    block_id: str
    alt_text: str | None  # wp:docPr/@descr
    title: str | None  # wp:docPr/@title
    decorative: bool  # adec:decorative extension
    inline: bool  # wp:inline vs wp:anchor (floating)
    width_px: int | None
    height_px: int | None
    image_sha256: str
    context_before: str  # at most 300 chars
    context_after: str  # at most 300 chars


class TableInfo(BaseModel):
    id: str
    block_id: str
    rows: int
    cols: int
    has_header_row: bool  # first row has w:tblHeader
    empty_cell_ratio: float
    has_merged_cells: bool


class LinkInfo(BaseModel):
    block_id: str
    text: str
    url: str | None
    external: bool


class ParsedDocument(BaseModel):
    meta: DocMeta
    blocks: list[Block]
    images: list[ImageInfo]
    tables: list[TableInfo]
    links: list[LinkInfo]
    slides: list[SlideInfo] = Field(default_factory=list)


class AuditOptions(BaseModel):
    """What a caller may choose per audit; everything else is server configuration."""

    mode: Literal["full", "rules_only"] = "full"
    target_grade: int | None = Field(default=None, ge=1, le=18)


class Location(BaseModel):
    block_id: str
    block_order: int
    snippet: str = Field(max_length=120)
    slide: int | None = None  # 1-based slide number for .pptx findings


class Finding(BaseModel):
    id: str
    rule_id: str
    title: str
    severity: Severity
    wcag_criterion: str | None
    wcag_level: WcagLevel
    location: Location
    message: str
    suggestion: str
    source: Source
    confidence: float = 1.0  # rules are always 1.0


class LlmUsage(BaseModel):
    provider: str
    model: str
    prompt_version: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    degraded: bool = False


class Report(BaseModel):
    report_version: str = "1.0"
    generated_at: datetime
    meta: DocMeta
    score: int  # 0-100
    counts: dict[Severity, int]
    findings: list[Finding]  # sorted by priority
    llm: LlmUsage | None
    mode: Literal["full", "rules_only"]
    warnings: list[str] = Field(default_factory=list)
