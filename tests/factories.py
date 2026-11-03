"""Builders for hand-made ``ParsedDocument`` objects used by the rule unit tests."""

from typing import Any

from accesslens.models import (
    Block,
    DocMeta,
    ImageInfo,
    LinkInfo,
    ParsedDocument,
    Run,
    TableInfo,
)


def block(
    order: int, text: str = "", type: str = "paragraph", level: int | None = None, **kw: Any
) -> Block:
    runs = kw.pop("runs", [Run(text=text)] if text else [])
    return Block(
        id=f"b{order:04d}",
        order=order,
        type=type,  # type: ignore[arg-type]
        text=text,
        heading_level=level,
        runs=runs,
        **kw,
    )


def heading(order: int, text: str, level: int = 1) -> Block:
    return block(order, text, "heading", level)


def image(order: int, **kw: Any) -> ImageInfo:
    defaults: dict[str, Any] = {
        "id": f"i{order:03d}",
        "block_id": f"b{order:04d}",
        "alt_text": "A bar chart of sales by quarter",
        "title": None,
        "decorative": False,
        "inline": True,
        "width_px": 240,
        "height_px": 160,
        "image_sha256": "0" * 64,
        "context_before": "",
        "context_after": "",
    }
    return ImageInfo(**{**defaults, **kw})


def table(order: int, **kw: Any) -> TableInfo:
    defaults: dict[str, Any] = {
        "id": f"t{order:03d}",
        "block_id": f"b{order:04d}",
        "rows": 3,
        "cols": 3,
        "has_header_row": True,
        "empty_cell_ratio": 0.0,
        "has_merged_cells": False,
    }
    return TableInfo(**{**defaults, **kw})


def link(order: int, text: str, url: str = "https://example.org/page") -> LinkInfo:
    return LinkInfo(block_id=f"b{order:04d}", text=text, url=url, external=True)


def doc(
    blocks: list[Block],
    *,
    images: list[ImageInfo] | None = None,
    tables: list[TableInfo] | None = None,
    links: list[LinkInfo] | None = None,
    title: str | None = "A document",
    language: str | None = "en-US",
    word_count: int | None = None,
) -> ParsedDocument:
    words = word_count if word_count is not None else sum(len(b.text.split()) for b in blocks)
    return ParsedDocument(
        meta=DocMeta(
            title=title,
            language=language,
            word_count=words,
            paragraph_count=len(blocks),
            image_count=len(images or []),
            table_count=len(tables or []),
            sha256="0" * 64,
        ),
        blocks=blocks,
        images=images or [],
        tables=tables or [],
        links=links or [],
    )


def good_doc() -> ParsedDocument:
    """A small document that violates no rule."""
    return doc(
        [
            heading(0, "Annual report", 1),
            block(1, "The team meets every Monday morning to plan the week."),
            heading(2, "Results", 2),
            block(3, "Sales rose in every quarter this year."),
        ]
    )
