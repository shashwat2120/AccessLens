"""Build a ``ParsedDocument`` from validated .docx bytes (TRD §3).

Call through ``sandbox.parse_in_sandbox``; this module assumes ``validate_docx`` has passed.
Block order is the index of each body-level paragraph or table, which is also the
``block_order`` used by the eval answer key. External relationships are recorded, never fetched.
Author and last-modified-by metadata are not read.
"""

import hashlib
import io
import re
from typing import Any

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.dml import MSO_COLOR_TYPE
from docx.oxml.ns import qn
from docx.text.hyperlink import Hyperlink
from docx.text.paragraph import Paragraph
from docx.text.run import Run as DocxRun

from accesslens.errors import AccessLensError, ParseFailedError
from accesslens.models import (
    Block,
    DocMeta,
    ImageInfo,
    LinkInfo,
    ParsedDocument,
    Run,
    TableInfo,
)

_HEADING = re.compile(r"^Heading (\d)$")
_EMU_PER_PIXEL = 9525
_CONTEXT_CHARS = 300
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


def parse_docx(data: bytes) -> ParsedDocument:
    """Parse ``data``; every failure surfaces as ``ParseFailedError``."""
    try:
        return _parse(data)
    except AccessLensError:
        raise
    except Exception as exc:  # malformed content must never escape as an arbitrary error
        raise ParseFailedError from exc


def _parse(data: bytes) -> ParsedDocument:
    doc = Document(io.BytesIO(data))
    blocks: list[Block] = []
    images: list[ImageInfo] = []
    tables: list[TableInfo] = []
    links: list[LinkInfo] = []
    table_words = 0

    body = doc.element.body
    elements = [e for e in body.iterchildren() if e.tag in (qn("w:p"), qn("w:tbl"))]
    for order, element in enumerate(elements):
        block_id = f"b{order:04d}"
        if element.tag == qn("w:p"):
            paragraph = Paragraph(element, doc)
            blocks.append(_paragraph_block(paragraph, order, block_id))
            paragraphs = [paragraph]
        else:
            blocks.append(Block(id=block_id, order=order, type="table", text=""))
            table_info, words = _table_info(element, block_id, len(tables))
            tables.append(table_info)
            table_words += words
            paragraphs = [Paragraph(p, doc) for p in element.iter(qn("w:p"))]
        for paragraph in paragraphs:
            links.extend(_links(paragraph, block_id))
        images.extend(_images(doc, element, block_id, len(images)))

    _add_image_context(blocks, images)
    word_count = sum(len(b.text.split()) for b in blocks) + table_words
    meta = DocMeta(
        title=doc.core_properties.title or None,
        language=_default_language(doc),
        word_count=word_count,
        paragraph_count=sum(1 for b in blocks if b.type != "table"),
        image_count=len(images),
        table_count=len(tables),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    return ParsedDocument(meta=meta, blocks=blocks, images=images, tables=tables, links=links)


def _paragraph_block(paragraph: Paragraph, order: int, block_id: str) -> Block:
    style_name = paragraph.style.name if paragraph.style is not None else None
    text = paragraph.text
    heading = _HEADING.match(style_name or "")
    has_numbering = paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None
    block_type: Any
    if heading:
        block_type = "heading"
    elif style_name == "Title":
        block_type = "title"
    elif not text.strip() and paragraph._p.xpath(".//w:drawing"):
        block_type = "image"
    elif has_numbering or (style_name or "").startswith("List"):
        block_type = "list_item"
    else:
        block_type = "paragraph"
    return Block(
        id=block_id,
        order=order,
        type=block_type,
        text=text,
        style_name=style_name,
        heading_level=int(heading.group(1)) if heading else None,
        runs=_runs(paragraph),
    )


def _runs(paragraph: Paragraph) -> list[Run]:
    result: list[Run] = []
    for item in paragraph.iter_inner_content():
        if isinstance(item, Hyperlink):
            url = item.url or (f"#{item.fragment}" if item.fragment else None)
            result.extend(_run(r, url) for r in item.runs)
        else:
            result.append(_run(item, None))
    return result


def _run(run: DocxRun, url: str | None) -> Run:
    color = run.font.color
    color_hex = None
    if color is not None and color.type == MSO_COLOR_TYPE.RGB and color.rgb is not None:
        color_hex = str(color.rgb)
    highlight = run.font.highlight_color
    size = run.font.size
    return Run(
        text=run.text,
        bold=bool(run.bold),
        italic=bool(run.italic),
        underline=bool(run.underline),
        size_pt=float(size.pt) if size is not None else None,
        color_hex=color_hex,
        highlight=highlight.name if highlight is not None else None,
        hyperlink_url=url,
    )


def _links(paragraph: Paragraph, block_id: str) -> list[LinkInfo]:
    return [
        LinkInfo(
            block_id=block_id,
            text=item.text,
            url=item.url or None,
            external=bool(item.address),
        )
        for item in paragraph.iter_inner_content()
        if isinstance(item, Hyperlink)
    ]


def _images(doc: DocxDocument, element: Any, block_id: str, start: int) -> list[ImageInfo]:
    found: list[ImageInfo] = []
    for drawing in element.iter(qn("wp:inline"), qn("wp:anchor")):
        docpr = drawing.find(qn("wp:docPr"))
        extent = drawing.find(qn("wp:extent"))
        cx = int(extent.get("cx", 0)) if extent is not None else 0
        cy = int(extent.get("cy", 0)) if extent is not None else 0
        decorative = docpr is not None and any(
            isinstance(e.tag, str)
            and e.tag.endswith("}decorative")
            and e.get("val", "").lower() in ("1", "true")
            for e in docpr.iter()
        )
        found.append(
            ImageInfo(
                id=f"i{start + len(found):03d}",
                block_id=block_id,
                alt_text=docpr.get("descr") if docpr is not None else None,
                title=docpr.get("title") if docpr is not None else None,
                decorative=decorative,
                inline=drawing.tag == qn("wp:inline"),
                width_px=cx // _EMU_PER_PIXEL or None,
                height_px=cy // _EMU_PER_PIXEL or None,
                image_sha256=_image_hash(doc, drawing),
                context_before="",
                context_after="",
            )
        )
    return found


def _image_hash(doc: DocxDocument, drawing: Any) -> str:
    """Hash of the embedded image bytes; linked (external) images have none to hash."""
    blip = drawing.find(".//" + qn("a:blip"))
    rel_id = blip.get(qn("r:embed")) if blip is not None else None
    part = doc.part.related_parts.get(rel_id) if rel_id else None
    return hashlib.sha256(part.blob).hexdigest() if part is not None else _EMPTY_SHA256


def _add_image_context(blocks: list[Block], images: list[ImageInfo]) -> None:
    for image in images:
        order = next(b.order for b in blocks if b.id == image.block_id)
        before = next((b.text for b in reversed(blocks[:order]) if b.text.strip()), "")
        after = next((b.text for b in blocks[order + 1 :] if b.text.strip()), "")
        image.context_before = before[-_CONTEXT_CHARS:]
        image.context_after = after[:_CONTEXT_CHARS]


def _table_info(table: Any, block_id: str, index: int) -> tuple[TableInfo, int]:
    rows = table.findall(qn("w:tr"))
    cells = list(table.iter(qn("w:tc")))
    texts = ["".join(tc.itertext()).strip() for tc in cells]
    grid = table.find(qn("w:tblGrid"))
    first_row_props = rows[0].find(qn("w:trPr")) if rows else None
    info = TableInfo(
        id=f"t{index:03d}",
        block_id=block_id,
        rows=len(rows),
        cols=len(grid.findall(qn("w:gridCol"))) if grid is not None else 0,
        has_header_row=first_row_props is not None
        and first_row_props.find(qn("w:tblHeader")) is not None,
        empty_cell_ratio=(sum(1 for t in texts if not t) / len(texts)) if texts else 0.0,
        has_merged_cells=any(_is_merged(tc) for tc in cells),
    )
    return info, sum(len(t.split()) for t in texts)


def _is_merged(cell: Any) -> bool:
    props = cell.find(qn("w:tcPr"))
    if props is None:
        return False
    if props.find(qn("w:vMerge")) is not None:
        return True
    span = props.find(qn("w:gridSpan"))
    return span is not None and int(span.get(qn("w:val"), 1)) > 1


def _default_language(doc: DocxDocument) -> str | None:
    values = doc.styles.element.xpath("w:docDefaults/w:rPrDefault/w:rPr/w:lang/@w:val")
    return str(values[0]) if values else None
