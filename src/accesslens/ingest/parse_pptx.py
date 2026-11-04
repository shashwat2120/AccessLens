"""Build a ``ParsedDocument`` from validated .pptx bytes.

Call through ``sandbox.parse_in_sandbox``; this module assumes ``validate_upload`` has passed.
It reads the package with the standard library zip reader and the hardened ``lxml`` parser, so
no presentation library (and no image library) is needed.

Every slide becomes a title block (always present, empty if the slide has no title) followed by
its text, pictures and tables in shape-tree order, which is the order a screen reader uses.
Block order is the global index of these blocks. Linked images and hyperlinks are recorded,
never fetched. Author and last-modified-by metadata are not read.
"""

import hashlib
import io
import posixpath
import zipfile
from collections import Counter
from collections.abc import Iterator
from typing import Any

from lxml import etree

from accesslens.errors import AccessLensError, ParseFailedError
from accesslens.ingest.validate import hardened_xml_parser
from accesslens.models import (
    Block,
    DocMeta,
    ImageInfo,
    LinkInfo,
    ParsedDocument,
    Run,
    SlideInfo,
    TableInfo,
)

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_DC = "http://purl.org/dc/elements/1.1/"
_EMU_PER_PIXEL = 9525
_CONTEXT_CHARS = 300
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_TITLE_TYPES = {"title", "ctrTitle"}
_FURNITURE_TYPES = {"dt", "ftr", "sldNum", "hdr"}  # repeated slide furniture, not content


def _q(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def parse_pptx(data: bytes) -> ParsedDocument:
    """Parse ``data``; every failure surfaces as ``ParseFailedError``."""
    try:
        return _parse(data, None)
    except AccessLensError:
        raise
    except Exception as exc:  # malformed content must never escape as an arbitrary error
        raise ParseFailedError from exc


def extract_image_blobs(data: bytes) -> dict[str, bytes]:
    """Embedded picture bytes keyed by ``ImageInfo.id``; linked pictures are absent."""
    try:
        blobs: dict[str, bytes] = {}
        _parse(data, blobs)
        return blobs
    except AccessLensError:
        raise
    except Exception as exc:
        raise ParseFailedError from exc


class _Package:
    """Read-only view of the zip with relationship lookups."""

    def __init__(self, archive: zipfile.ZipFile) -> None:
        self.archive = archive
        self.names = set(archive.namelist())

    def xml(self, path: str) -> Any:
        return etree.fromstring(self.archive.read(path), parser=hardened_xml_parser())

    def resolve(self, base_dir: str, target: str) -> str | None:
        path = target.lstrip("/") if target.startswith("/") else posixpath.join(base_dir, target)
        path = posixpath.normpath(path)
        return path if path in self.names else None

    def relationships(self, part: str) -> dict[str, tuple[str, bool]]:
        """Relationship id -> (target, is_external) for ``part``."""
        folder, name = posixpath.split(part)
        rels_path = posixpath.join(folder, "_rels", name + ".rels")
        if rels_path not in self.names:
            return {}
        return {
            rel.get("Id", ""): (rel.get("Target", ""), rel.get("TargetMode") == "External")
            for rel in self.xml(rels_path).iter(_q(_REL, "Relationship"))
        }


def _parse(data: bytes, keep_blobs: dict[str, bytes] | None) -> ParsedDocument:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        pkg = _Package(archive)
        builder = _Builder(pkg, keep_blobs)
        presentation = pkg.xml("ppt/presentation.xml")
        rels = pkg.relationships("ppt/presentation.xml")
        for slide_id in presentation.iter(_q(_P, "sldId")):
            target = rels.get(slide_id.get(_q(_R, "id"), ""))
            path = pkg.resolve("ppt", target[0]) if target else None
            if path:
                builder.add_slide(path)
        title = _core_title(pkg)
        language = builder.language() or _default_language(presentation)

    blocks = builder.blocks
    meta = DocMeta(
        title=title,
        language=language,
        word_count=sum(len(b.text.split()) for b in blocks) + builder.table_words,
        paragraph_count=sum(1 for b in blocks if b.type != "table"),
        image_count=len(builder.images),
        table_count=len(builder.tables),
        sha256=hashlib.sha256(data).hexdigest(),
        kind="pptx",
    )
    _add_image_context(blocks, builder.images)
    return ParsedDocument(
        meta=meta,
        blocks=blocks,
        images=builder.images,
        tables=builder.tables,
        links=builder.links,
        slides=builder.slides,
    )


class _Builder:
    def __init__(self, pkg: _Package, keep_blobs: dict[str, bytes] | None) -> None:
        self.pkg = pkg
        self.keep_blobs = keep_blobs
        self.blocks: list[Block] = []
        self.images: list[ImageInfo] = []
        self.tables: list[TableInfo] = []
        self.links: list[LinkInfo] = []
        self.slides: list[SlideInfo] = []
        self.table_words = 0
        self._langs: Counter[str] = Counter()

    def language(self) -> str | None:
        return self._langs.most_common(1)[0][0] if self._langs else None

    def _add(self, **fields: Any) -> Block:
        block = Block(id=f"b{len(self.blocks):04d}", order=len(self.blocks), **fields)
        self.blocks.append(block)
        return block

    def add_slide(self, path: str) -> None:
        number = len(self.slides) + 1
        root = self.pkg.xml(path)
        rels = self.pkg.relationships(path)
        tree = root.find(f"{_q(_P, 'cSld')}/{_q(_P, 'spTree')}")
        shapes = list(_shapes(tree)) if tree is not None else []

        title_shape = next((s for s in shapes if _is_title(s)), None)
        title_text = _shape_text(title_shape) if title_shape is not None else ""
        title_block = self._add(type="heading", text=title_text, heading_level=1, slide=number)

        reading_order: list[Any] = []
        empty_placeholders = 0
        for shape in shapes:
            if _is_furniture(shape):
                continue  # footer, date and slide number are not slide content
            if shape is title_shape:
                reading_order.append(shape)
            elif shape.tag == _q(_P, "sp"):
                if self._add_text_shape(shape, rels, number):
                    reading_order.append(shape)
                elif _placeholder(shape) is not None:
                    empty_placeholders += 1
            elif shape.tag == _q(_P, "pic"):
                self._add_picture(shape, rels, path, number)
                reading_order.append(shape)
            elif (
                shape.tag == _q(_P, "graphicFrame")
                and shape.find(f".//{_q(_A, 'tbl')}") is not None
            ):
                self._add_table(shape, number)
                reading_order.append(shape)
        for lang in root.iter(_q(_A, "rPr"), _q(_A, "endParaRPr")):
            if lang.get("lang"):
                self._langs[lang.get("lang", "")] += 1
        self.slides.append(
            SlideInfo(
                number=number,
                block_id=title_block.id,
                title=title_text,
                has_title_placeholder=title_shape is not None,
                title_is_first=title_shape is None
                or (bool(reading_order) and reading_order[0] is title_shape),
                empty_placeholders=empty_placeholders,
            )
        )

    def _add_text_shape(self, shape: Any, rels: dict[str, tuple[str, bool]], slide: int) -> bool:
        """Add a block per non-empty paragraph; return whether the shape had any text."""
        found = False
        for paragraph in shape.iterfind(f"{_q(_P, 'txBody')}/{_q(_A, 'p')}"):
            text = _paragraph_text(paragraph)
            if not text.strip():
                continue
            found = True
            block_id = f"b{len(self.blocks):04d}"  # the id _add is about to assign
            self._add(
                type="list_item" if _is_bulleted(paragraph) else "paragraph",
                text=text,
                runs=self._runs(paragraph, rels, block_id),
                slide=slide,
            )
        return found

    def _runs(self, paragraph: Any, rels: dict[str, tuple[str, bool]], block_id: str) -> list[Run]:
        runs: list[Run] = []
        open_link: tuple[str, list[str]] | None = None  # (relationship id, text parts)
        for element in paragraph:
            if element.tag not in (_q(_A, "r"), _q(_A, "fld")):
                continue
            text = "".join(t.text or "" for t in element.iterfind(_q(_A, "t")))
            props = element.find(_q(_A, "rPr"))
            link = props.find(_q(_A, "hlinkClick")) if props is not None else None
            rid = link.get(_q(_R, "id")) if link is not None else None
            url = _target(rels, rid)
            runs.append(_run(text, props, url))
            if rid and open_link and open_link[0] == rid:
                open_link[1].append(text)
            else:
                self._close_link(open_link, rels, block_id)
                open_link = (rid, [text]) if rid else None
        self._close_link(open_link, rels, block_id)
        return runs

    def _close_link(
        self,
        link: tuple[str, list[str]] | None,
        rels: dict[str, tuple[str, bool]],
        block_id: str,
    ) -> None:
        if link is None:
            return
        target = rels.get(link[0])
        self.links.append(
            LinkInfo(
                block_id=block_id,
                text="".join(link[1]),
                url=target[0] if target else None,
                external=bool(target and target[1]),
            )
        )

    def _add_picture(
        self, shape: Any, rels: dict[str, tuple[str, bool]], slide_path: str, slide: int
    ) -> None:
        block = self._add(type="image", text="", slide=slide)
        props = shape.find(f"{_q(_P, 'nvPicPr')}/{_q(_P, 'cNvPr')}")
        extent = shape.find(f"{_q(_P, 'spPr')}/{_q(_A, 'xfrm')}/{_q(_A, 'ext')}")
        decorative = props is not None and any(
            isinstance(e.tag, str)
            and e.tag.endswith("}decorative")
            and e.get("val", "").lower() in ("1", "true")
            for e in props.iter()
        )
        image_id = f"i{len(self.images):03d}"
        blip = shape.find(f".//{_q(_A, 'blip')}")
        rid = blip.get(_q(_R, "embed")) if blip is not None else None
        target = rels.get(rid or "")
        blob_path = (
            self.pkg.resolve(posixpath.dirname(slide_path), target[0])
            if target and not target[1]
            else None
        )
        blob = self.pkg.archive.read(blob_path) if blob_path else None
        if blob is not None and self.keep_blobs is not None:
            self.keep_blobs[image_id] = blob
        cx = int(extent.get("cx", 0)) if extent is not None else 0
        cy = int(extent.get("cy", 0)) if extent is not None else 0
        self.images.append(
            ImageInfo(
                id=image_id,
                block_id=block.id,
                alt_text=props.get("descr") if props is not None else None,
                title=props.get("title") if props is not None else None,
                decorative=decorative,
                inline=True,  # slides have no text flow, so nothing floats
                width_px=cx // _EMU_PER_PIXEL or None,
                height_px=cy // _EMU_PER_PIXEL or None,
                image_sha256=hashlib.sha256(blob).hexdigest()
                if blob is not None
                else _EMPTY_SHA256,
                context_before="",
                context_after="",
            )
        )

    def _add_table(self, shape: Any, slide: int) -> None:
        block = self._add(type="table", text="", slide=slide)
        table = shape.find(f".//{_q(_A, 'tbl')}")
        rows = table.findall(_q(_A, "tr"))
        cells = list(table.iter(_q(_A, "tc")))
        texts = ["".join(t.text or "" for t in tc.iter(_q(_A, "t"))).strip() for tc in cells]
        grid = table.find(_q(_A, "tblGrid"))
        props = table.find(_q(_A, "tblPr"))
        self.tables.append(
            TableInfo(
                id=f"t{len(self.tables):03d}",
                block_id=block.id,
                rows=len(rows),
                cols=len(grid.findall(_q(_A, "gridCol"))) if grid is not None else 0,
                has_header_row=props is not None and props.get("firstRow") in ("1", "true"),
                empty_cell_ratio=(sum(1 for t in texts if not t) / len(texts)) if texts else 0.0,
                has_merged_cells=any(_is_merged(tc) for tc in cells),
            )
        )
        self.table_words += sum(len(t.split()) for t in texts)


def _shapes(tree: Any) -> Iterator[Any]:
    """Shapes in shape-tree order (the screen-reader order), flattening groups."""
    for child in tree:
        if child.tag == _q(_P, "grpSp"):
            yield from _shapes(child)
        elif child.tag in (_q(_P, "sp"), _q(_P, "pic"), _q(_P, "graphicFrame")):
            yield child


def _placeholder(shape: Any) -> Any:
    return shape.find(f"{_q(_P, 'nvSpPr')}/{_q(_P, 'nvPr')}/{_q(_P, 'ph')}")


def _is_furniture(shape: Any) -> bool:
    ph = _placeholder(shape) if shape.tag == _q(_P, "sp") else None
    return ph is not None and ph.get("type") in _FURNITURE_TYPES


def _is_title(shape: Any) -> bool:
    ph = _placeholder(shape) if shape.tag == _q(_P, "sp") else None
    return ph is not None and ph.get("type") in _TITLE_TYPES


def _paragraph_text(paragraph: Any) -> str:
    parts: list[str] = []
    for element in paragraph:
        if element.tag in (_q(_A, "r"), _q(_A, "fld")):
            parts.extend(t.text or "" for t in element.iterfind(_q(_A, "t")))
        elif element.tag == _q(_A, "br"):
            parts.append(" ")
    return "".join(parts)


def _shape_text(shape: Any) -> str:
    paragraphs = shape.iterfind(f"{_q(_P, 'txBody')}/{_q(_A, 'p')}")
    return " ".join(t.strip() for t in (_paragraph_text(p) for p in paragraphs) if t.strip())


def _is_bulleted(paragraph: Any) -> bool:
    props = paragraph.find(_q(_A, "pPr"))
    if props is None:
        return False
    if props.find(_q(_A, "buNone")) is not None:
        return False
    return (
        props.find(_q(_A, "buChar")) is not None
        or props.find(_q(_A, "buAutoNum")) is not None
        or int(props.get("lvl", 0) or 0) > 0
    )


def _target(rels: dict[str, tuple[str, bool]], rid: str | None) -> str | None:
    target = rels.get(rid or "")
    return target[0] if target else None


def _run(text: str, props: Any, url: str | None) -> Run:
    size = props.get("sz") if props is not None else None
    colour = props.find(f"{_q(_A, 'solidFill')}/{_q(_A, 'srgbClr')}") if props is not None else None
    underline = props is not None and props.get("u", "none") != "none"
    return Run(
        text=text,
        bold=props is not None and props.get("b") in ("1", "true"),
        italic=props is not None and props.get("i") in ("1", "true"),
        underline=underline,
        size_pt=int(size) / 100 if size and size.isdigit() else None,
        color_hex=colour.get("val") if colour is not None else None,
        hyperlink_url=url,
    )


def _is_merged(cell: Any) -> bool:
    for attr in ("gridSpan", "rowSpan"):
        value = cell.get(attr, "")
        if value.isdigit() and int(value) > 1:
            return True
    return cell.get("hMerge") in ("1", "true") or cell.get("vMerge") in ("1", "true")


def _core_title(pkg: _Package) -> str | None:
    if "docProps/core.xml" not in pkg.names:
        return None
    node = pkg.xml("docProps/core.xml").find(_q(_DC, "title"))
    return (node.text or "").strip() or None if node is not None else None


def _default_language(presentation: Any) -> str | None:
    for node in presentation.iter(_q(_A, "defRPr")):
        if node.get("lang"):
            return str(node.get("lang"))
    return None


def _add_image_context(blocks: list[Block], images: list[ImageInfo]) -> None:
    for image in images:
        order = next(b.order for b in blocks if b.id == image.block_id)
        before = next((b.text for b in reversed(blocks[:order]) if b.text.strip()), "")
        after = next((b.text for b in blocks[order + 1 :] if b.text.strip()), "")
        image.context_before = before[-_CONTEXT_CHARS:]
        image.context_after = after[:_CONTEXT_CHARS]
