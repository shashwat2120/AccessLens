"""Synthetic .pptx corpus with planted accessibility problems.

Decks are written as raw OOXML with the standard library only, so the files are deterministic and
need no presentation library. ``build_decks`` returns the decks and, for each, the issues that were
planted (rule id and block order); ``generate_corpus.generate`` writes them and the answer key.
Block order follows ``accesslens.ingest.parse_pptx``: every slide starts with a title block
(empty if the slide has no title), then its text paragraphs, pictures and tables in shape order.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

NS = (
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
)
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PPTX_MAIN = "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
_SLIDE_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
_FIXED_TIME = (2024, 1, 1, 0, 0, 0)
_PICTURE_EMU = (2286000, 1524000)

BODY_LINES = [
    "Revenue grew steadily this year.",
    "Support tickets fell by a third.",
    "The new office opened in March.",
    "Training reached every team.",
    "Customers rated service highly.",
]


@dataclass
class Planted:
    rule_id: str
    block_order: int
    notes: str


@dataclass
class Slide:
    deck: Deck
    number: int
    title_order: int  # every slide has a title block, even when it has no title
    shapes: list[str] = field(default_factory=list)
    rels: list[tuple[str, str, str, bool]] = field(default_factory=list)  # id, type, target, ext
    _next_id: int = 2

    def _shape_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _run(self, text: str, *, size: int | None = None, underline: bool = False) -> str:
        lang = f' lang="{self.deck.lang}"' if self.deck.lang else ""
        sz = f' sz="{size * 100}"' if size else ""
        u = ' u="sng"' if underline else ""
        return f"<a:r><a:rPr{lang}{sz}{u}/><a:t>{escape(text)}</a:t></a:r>"

    def _paragraph(self, runs: str, *, bullet: bool = False) -> str:
        props = (
            '<a:pPr marL="342900" indent="-342900"><a:buChar char="&#8226;"/></a:pPr>'
            if bullet
            else ""
        )
        return f"<a:p>{props}{runs}</a:p>"

    def title(self, text: str) -> int:
        self.shapes.append(
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title 1"/><p:cNvSpPr/>'
            '<p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/>'
            f"<a:lstStyle/>{self._paragraph(self._run(text))}</p:txBody></p:sp>"
        )
        return self.title_order

    def text(
        self,
        lines: list[str],
        *,
        size: int | None = 24,
        bullets: bool = True,
        underline: bool = False,
        placeholder: bool = True,
    ) -> list[int]:
        ph = '<p:ph type="body" idx="1"/>' if placeholder else ""
        box = "" if placeholder else ' txBox="1"'
        paragraphs = "".join(
            self._paragraph(self._run(t, size=size, underline=underline), bullet=bullets)
            for t in lines
        )
        self.shapes.append(
            f'<p:sp><p:nvSpPr><p:cNvPr id="{self._shape_id()}" name="Content"/>'
            f"<p:cNvSpPr{box}/><p:nvPr>{ph}</p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/>"
            f"<a:lstStyle/>{paragraphs}</p:txBody></p:sp>"
        )
        return [self.deck.next_order() for _ in lines]

    def empty_placeholder(self) -> None:
        self.shapes.append(
            f'<p:sp><p:nvSpPr><p:cNvPr id="{self._shape_id()}" name="Content Placeholder"/>'
            '<p:cNvSpPr/><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:spPr/>'
            "<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr/></a:p></p:txBody></p:sp>"
        )

    def link(self, before: str, link_text: str, url: str) -> int:
        rid = f"rId{len(self.rels) + 1}"
        self.rels.append((rid, f"{_REL_TYPE}/hyperlink", url, True))
        lang = f' lang="{self.deck.lang}"' if self.deck.lang else ""
        runs = (
            self._run(before, size=24)
            + f'<a:r><a:rPr{lang} sz="2400"><a:hlinkClick r:id="{rid}"/></a:rPr>'
            f"<a:t>{escape(link_text)}</a:t></a:r>"
        )
        self.shapes.append(
            f'<p:sp><p:nvSpPr><p:cNvPr id="{self._shape_id()}" name="Link"/><p:cNvSpPr txBox="1"/>'
            f"<p:nvPr/></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>"
            f"{self._paragraph(runs)}</p:txBody></p:sp>"
        )
        return self.deck.next_order()

    def picture(self, alt: str | None) -> int:
        rid = f"rId{len(self.rels) + 1}"
        self.rels.append((rid, f"{_REL_TYPE}/image", "../media/image1.png", False))
        descr = f' descr="{escape(alt, {chr(34): "&quot;"})}"' if alt is not None else ""
        cx, cy = _PICTURE_EMU
        self.shapes.append(
            f'<p:pic><p:nvPicPr><p:cNvPr id="{self._shape_id()}" name="Picture"{descr}/>'
            "<p:cNvPicPr/><p:nvPr/></p:nvPicPr>"
            f'<p:blipFill><a:blip r:embed="{rid}"/></p:blipFill><p:spPr><a:xfrm>'
            f'<a:off x="914400" y="2400000"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm></p:spPr></p:pic>'
        )
        return self.deck.next_order()

    def table(self, rows: list[list[str]], *, header: bool = True, merged: bool = False) -> int:
        cols = len(rows[0])
        first = ' firstRow="1"' if header else ""
        grid = "".join('<a:gridCol w="1828800"/>' for _ in range(cols))
        body = []
        for r, row in enumerate(rows):
            cells = []
            for c, value in enumerate(row):
                span = ' gridSpan="2"' if merged and r == 1 and c == 0 else ""
                run = self._run(value, size=20) if value else ""
                cells.append(
                    f"<a:tc{span}><a:txBody><a:bodyPr/><a:lstStyle/><a:p>{run}</a:p>"
                    "</a:txBody><a:tcPr/></a:tc>"
                )
            body.append(f'<a:tr h="370840">{"".join(cells)}</a:tr>')
        self.shapes.append(
            f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{self._shape_id()}" name="Table"/>'
            "<p:cNvGraphicFramePr/><p:nvPr/></p:nvGraphicFramePr><p:xfrm>"
            '<a:off x="914400" y="4200000"/><a:ext cx="5486400" cy="1112520"/></p:xfrm>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">'
            f"<a:tbl><a:tblPr{first}/><a:tblGrid>{grid}</a:tblGrid>{''.join(body)}</a:tbl>"
            "</a:graphicData></a:graphic></p:graphicFrame>"
        )
        return self.deck.next_order()

    def xml(self) -> str:
        return (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sld {NS}><p:cSld><p:spTree>'
            '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            f"<p:grpSpPr/>{''.join(self.shapes)}</p:spTree></p:cSld></p:sld>"
        )

    def rels_xml(self) -> str:
        items = "".join(
            f'<Relationship Id="{rid}" Type="{kind}" Target="{escape(target)}"'
            f"{' TargetMode="External"' if external else ''}/>"
            for rid, kind, target, external in self.rels
        )
        head = f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{_REL_NS}">'
        return f"{head}{items}</Relationships>"


@dataclass
class Deck:
    doc_id: str
    png: bytes
    title: str | None = "Quarterly update"
    lang: str | None = "en-US"
    slides: list[Slide] = field(default_factory=list)
    planted: list[Planted] = field(default_factory=list)
    _order: int = 0

    def next_order(self) -> int:
        order = self._order
        self._order += 1
        return order

    def slide(self) -> Slide:
        slide = Slide(self, len(self.slides) + 1, self.next_order())
        self.slides.append(slide)
        return slide

    def expect(self, rule_id: str, block_order: int, notes: str) -> None:
        self.planted.append(Planted(rule_id, block_order, notes))

    def to_bytes(self) -> bytes:
        n = len(self.slides)
        overrides = "".join(
            f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="{_SLIDE_TYPE}"/>'
            for i in range(1, n + 1)
        )
        ids = "".join(f'<p:sldId id="{255 + i}" r:id="rId{i}"/>' for i in range(1, n + 1))
        pres_rels = "".join(
            f'<Relationship Id="rId{i}" Type="{_REL_TYPE}/slide" Target="slides/slide{i}.xml"/>'
            for i in range(1, n + 1)
        )
        core = (
            '<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<dc:title>{escape(self.title)}</dc:title></cp:coreProperties>"
            if self.title
            else None
        )
        parts: dict[str, bytes | str] = {
            "[Content_Types].xml": (
                '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats'
                '.org/package/2006/content-types"><Default Extension="rels" ContentType="'
                'application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Default Extension="png" ContentType="image/png"/>'
                f'<Override PartName="/ppt/presentation.xml" ContentType="{_PPTX_MAIN}"/>'
                f"{overrides}"
                "</Types>"
            ),
            "_rels/.rels": (
                f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{_REL_NS}">'
                f'<Relationship Id="rId1" Type="{_REL_TYPE}/officeDocument" '
                'Target="ppt/presentation.xml"/></Relationships>'
            ),
            "ppt/presentation.xml": (
                f'<?xml version="1.0" encoding="UTF-8"?><p:presentation {NS}>'
                f"<p:sldIdLst>{ids}</p:sldIdLst></p:presentation>"
            ),
            "ppt/_rels/presentation.xml.rels": (
                f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{_REL_NS}">'
                f"{pres_rels}</Relationships>"
            ),
            "ppt/media/image1.png": self.png,
        }
        if core:
            parts["docProps/core.xml"] = core
        for slide in self.slides:
            parts[f"ppt/slides/slide{slide.number}.xml"] = slide.xml()
            if slide.rels:
                parts[f"ppt/slides/_rels/slide{slide.number}.xml.rels"] = slide.rels_xml()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in parts.items():
                info = zipfile.ZipInfo(name, _FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content)
        return buffer.getvalue()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.to_bytes())


def _good_slide(deck: Deck, title: str, line: int = 0) -> Slide:
    slide = deck.slide()
    slide.title(title)
    slide.text(BODY_LINES[line : line + 2])
    return slide


def _base(
    doc_id: str, png: bytes, *, title: str | None = "Quarterly update", lang: str | None = "en-US"
) -> Deck:
    deck = Deck(doc_id, png, title=title, lang=lang)
    _good_slide(deck, "Welcome")
    return deck


def _sld001(doc_id: str, png: bytes, k: int) -> Deck:
    deck = _base(doc_id, png)
    slide = deck.slide()
    slide.text([BODY_LINES[k], BODY_LINES[k + 1]])
    deck.expect("SLD-001", slide.title_order, "slide with no title")
    _good_slide(deck, "Next steps", 2)
    return deck


def _sld002(doc_id: str, png: bytes, k: int) -> Deck:
    deck = _base(doc_id, png)
    _good_slide(deck, f"Results {k}", 1)
    slide = _good_slide(deck, f"Results {k}", 2)
    deck.expect("SLD-002", slide.title_order, "same title as an earlier slide")
    return deck


def _sld003(doc_id: str, png: bytes, k: int) -> Deck:
    deck = _base(doc_id, png)
    slide = deck.slide()
    slide.text([BODY_LINES[k]])
    slide.title(f"Overview {k}")
    deck.expect("SLD-003", slide.title_order, "title comes after the body in reading order")
    return deck


def _sld004(doc_id: str, png: bytes, k: int) -> Deck:
    deck = _base(doc_id, png)
    slide = deck.slide()
    slide.title(f"Fine print {k}")
    orders = slide.text([BODY_LINES[k]], size=9)
    deck.expect("SLD-004", orders[0], "9 pt text on a slide")
    return deck


def _sld005(doc_id: str, png: bytes, k: int) -> Deck:
    deck = _base(doc_id, png)
    slide = deck.slide()
    slide.title(f"Agenda {k}")
    slide.empty_placeholder()
    deck.expect("SLD-005", slide.title_order, "empty content placeholder")
    return deck


def _images(doc_id: str, png: bytes, k: int) -> Deck:
    deck = _base(doc_id, png)
    slide = deck.slide()
    slide.title(f"Chart {k}")
    deck.expect("IMG-001", slide.picture(None), "picture without alt text")
    deck.expect("IMG-002", slide.picture("image"), "placeholder alt text")
    return deck


def _table_link(doc_id: str, png: bytes, k: int) -> Deck:
    deck = _base(doc_id, png)
    slide = deck.slide()
    slide.title(f"Data {k}")
    deck.expect(
        "TBL-001",
        slide.table([["Team", "Score"], ["North", "7"], ["South", "9"]], header=False),
        "no header row",
    )
    deck.expect(
        "LNK-001",
        slide.link("For details ", "click here", "https://example.org/report"),
        "vague link",
    )
    return deck


def _doc_props(doc_id: str, png: bytes, k: int) -> Deck:
    deck = _base(doc_id, png, title=None, lang=None)
    deck.expect("DOC-001", 0, "no document title")
    deck.expect("DOC-002", 0, "no language set")
    return deck


GROUPS = (_sld001, _sld002, _sld003, _sld004, _sld005, _images, _table_link, _doc_props)


def _clean(doc_id: str, png: bytes, k: int) -> Deck:
    deck = _base(doc_id, png)
    slide = _good_slide(deck, "Highlights", 2)
    slide.picture("Bar chart of sales by quarter, rising each quarter")
    slide = deck.slide()
    slide.title("Team scores")
    slide.table([["Team", "Score"], ["North", "7"], ["South", "9"]])
    slide.link("Read the ", "annual report", "https://example.org/annual-report")
    return deck


def build_decks(png: bytes) -> list[tuple[str, Deck]]:
    """(folder, deck) pairs: three planted variants per group, plus three clean decks."""
    decks: list[tuple[str, Deck]] = []
    n = 0
    for build in GROUPS:
        for k in range(3):
            n += 1
            decks.append(("pptx", build(f"syn-p{n:02d}", png, k)))
    decks += [("pptx", _clean(f"clean-p{i}", png, i)) for i in range(1, 4)]
    return decks


def sample_deck(png: bytes) -> Deck:
    """A small synthetic deck for the UI's "try a sample" button; every severity appears."""
    deck = Deck("sample-team-update", png, title=None, lang="en-US")
    _good_slide(deck, "Team update")
    slide = deck.slide()
    slide.text(["Revenue grew steadily this year.", "Support tickets fell by a third."])
    slide = deck.slide()
    slide.title("Results")
    slide.picture(None)
    slide.text(["Customers rated service highly."], size=9)
    slide = deck.slide()
    slide.text(["The new office opened in March."])
    slide.title("Results")
    slide.empty_placeholder()
    slide = deck.slide()
    slide.title("Scores")
    slide.table([["Team", "Score"], ["North", "7"], ["South", "9"]], header=False)
    slide.link("For details ", "click here", "https://example.org/report")
    return deck
