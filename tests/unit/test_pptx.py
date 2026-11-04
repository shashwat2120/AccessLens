import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from generate_corpus import bar_chart_png
from generate_pptx import Deck, build_decks, sample_deck

from accesslens.config import Settings
from accesslens.errors import InvalidFileError, MacroEnabledError
from accesslens.ingest.parse_docx import parse_docx
from accesslens.ingest.parse_pptx import extract_image_blobs, parse_pptx
from accesslens.ingest.sandbox import extract_images_in_sandbox, parse_in_sandbox
from accesslens.ingest.validate import (
    MAIN_CONTENT_TYPE,
    PPTX_MAIN_CONTENT_TYPE,
    validate_docx,
    validate_upload,
)
from accesslens.models import AuditOptions
from accesslens.rules import REGISTRY, run_rules
from accesslens.rules.base import kinds_for
from accesslens.rules.catalog import rule_catalog
from fakes import service_for

PNG = bar_chart_png([3, 5, 8, 6])
FURNITURE = (
    '<p:sp><p:nvSpPr><p:cNvPr id="90" name="Footer"/><p:cNvSpPr/><p:nvPr><p:ph type="{kind}"/>'
    "</p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p>{runs}</a:p></p:txBody></p:sp>"
)


def rebuilt(data: bytes, replacements: dict[str, bytes]) -> bytes:
    """A copy of a package with some parts replaced."""
    out = BytesIO()
    with zipfile.ZipFile(BytesIO(data)) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            dst.writestr(info.filename, replacements.get(info.filename, src.read(info)))
    return out.getvalue()


def test_every_planted_issue_is_found_and_clean_decks_are_clean() -> None:
    for _, deck in build_decks(PNG):
        findings, warnings = run_rules(parse_pptx(deck.to_bytes()))
        assert not warnings
        found = {(f.rule_id, f.location.block_order) for f in findings}
        planted = {(p.rule_id, p.block_order) for p in deck.planted}
        assert found == planted, deck.doc_id


def test_parser_reads_structure_links_tables_pictures_and_properties() -> None:
    deck = Deck("t", PNG, title="Roadmap", lang="en-GB")
    slide = deck.slide()
    slide.title("Plan")
    slide.text(["First point.", "Second point."], size=20)
    slide.picture("A bar chart")
    slide.table([["A", "B"], ["1", "2"]], merged=True)
    slide.link("See ", "the plan", "https://example.org/plan")
    doc = parse_pptx(deck.to_bytes())

    assert doc.meta.kind == "pptx"
    assert (doc.meta.title, doc.meta.language) == ("Roadmap", "en-GB")
    assert [b.type for b in doc.blocks] == [
        "heading",
        "list_item",
        "list_item",
        "image",
        "table",
        "paragraph",
    ]
    assert {b.slide for b in doc.blocks} == {1}
    assert doc.blocks[1].runs[0].size_pt == 20
    assert doc.images[0].alt_text == "A bar chart" and doc.images[0].inline
    assert doc.tables[0].has_header_row and doc.tables[0].has_merged_cells
    assert [(link.text, link.url, link.external) for link in doc.links] == [
        ("the plan", "https://example.org/plan", True)
    ]
    assert doc.links[0].block_id == doc.blocks[-1].id
    assert doc.images[0].context_before == "Second point."
    assert doc.slides[0].title == "Plan" and doc.slides[0].title_is_first


def test_footer_date_and_slide_number_are_not_content() -> None:
    deck = Deck("t", PNG)
    slide = deck.slide()
    slide.title("Plan")
    slide.shapes.insert(0, FURNITURE.format(kind="sldNum", runs="<a:r><a:t>1</a:t></a:r>"))
    slide.shapes.append(FURNITURE.format(kind="ftr", runs="<a:endParaRPr/>"))
    doc = parse_pptx(deck.to_bytes())
    findings, _ = run_rules(doc)
    assert [b.type for b in doc.blocks] == ["heading"]
    assert doc.slides[0].title_is_first and doc.slides[0].empty_placeholders == 0
    assert not findings


def test_extracted_images_follow_the_same_ids_as_the_parser() -> None:
    deck = sample_deck(PNG)
    data = deck.to_bytes()
    blobs = extract_image_blobs(data)
    assert set(blobs) == {i.id for i in parse_pptx(data).images}
    assert blobs["i000"] == PNG


def test_a_relationship_pointing_outside_the_package_is_ignored() -> None:
    deck = Deck("t", PNG)
    slide = deck.slide()
    slide.title("Plan")
    slide.picture("A chart")
    slide.rels[0] = (slide.rels[0][0], slide.rels[0][1], "../../../../etc/passwd", False)
    doc = parse_pptx(deck.to_bytes())
    assert doc.images[0].alt_text == "A chart"
    assert extract_image_blobs(deck.to_bytes()) == {}


def test_validate_upload_tells_the_formats_apart() -> None:
    deck = sample_deck(PNG).to_bytes()
    assert validate_upload(deck)[1] == "pptx"
    with pytest.raises(InvalidFileError):
        validate_docx(deck)  # a deck is not a Word document


def test_macro_enabled_presentations_and_doctypes_are_rejected() -> None:
    data = sample_deck(PNG).to_bytes()
    macro = "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml"
    types = zipfile.ZipFile(BytesIO(data)).read("[Content_Types].xml").decode()
    with pytest.raises(MacroEnabledError):
        validate_upload(
            rebuilt(
                data, {"[Content_Types].xml": types.replace(PPTX_MAIN_CONTENT_TYPE, macro).encode()}
            )
        )
    with pytest.raises(InvalidFileError):
        validate_upload(
            rebuilt(data, {"ppt/slides/slide1.xml": b'<!DOCTYPE x [<!ENTITY a "b">]><x/>'})
        )
    with pytest.raises(InvalidFileError):  # a package cannot claim to be both formats
        both = types.replace(
            "</Types>",
            f'<Override PartName="/word/document.xml" ContentType="{MAIN_CONTENT_TYPE}"/></Types>',
        )
        validate_upload(rebuilt(data, {"[Content_Types].xml": both.encode()}))


def test_each_rule_applies_to_the_right_formats() -> None:
    assert kinds_for("SLD-001") == {"pptx"}
    assert kinds_for("HDG-002") == {"docx"}
    assert kinds_for("CLR-001") == {"docx"}
    assert kinds_for("IMG-001") == {"docx", "pptx"}
    assert all(kinds_for(r) == {"pptx"} for r in REGISTRY if r.startswith("SLD-"))


def test_word_rules_do_not_run_on_slides_and_slide_rules_do_not_run_on_word(
    corpus: tuple[Path, Path],
) -> None:
    deck = Deck("t", PNG)
    slide = deck.slide()
    slide.text(["Words " * 400], bullets=False)  # long, no headings, big text
    findings, _ = run_rules(parse_pptx(deck.to_bytes()))
    assert not {f.rule_id for f in findings} & {"HDG-001", "HDG-005", "CLR-001", "TXT-001"}
    docx = parse_docx((corpus[0] / "synthetic" / "syn-01.docx").read_bytes())
    assert not {f.rule_id for f in run_rules(docx)[0] if f.rule_id.startswith("SLD-")}


def test_every_slide_rule_has_guidance_in_the_public_catalog() -> None:
    slide_rules = {r.id for r in rule_catalog() if r.id.startswith("SLD-")}
    assert slide_rules == {f"SLD-00{i}" for i in range(1, 6)}


def test_the_sandbox_parses_and_extracts_decks_in_a_child_process() -> None:
    data = sample_deck(PNG).to_bytes()
    cfg = Settings(_env_file=None)
    doc = parse_in_sandbox(data, cfg)
    assert doc.meta.kind == "pptx" and len(doc.slides) == 5
    assert extract_images_in_sandbox(data, cfg)["i000"] == PNG


def test_the_sandbox_rejects_a_bad_deck_generically() -> None:
    cfg = Settings(_env_file=None)
    broken = rebuilt(sample_deck(PNG).to_bytes(), {"ppt/presentation.xml": b"<not-xml"})
    with pytest.raises(Exception) as caught:
        parse_in_sandbox(broken, cfg)
    assert "not-xml" not in str(caught.value)


def test_the_audit_service_reports_slide_numbers_for_decks() -> None:
    service = service_for(Settings(_env_file=None, llm_enabled=False))
    report = service.audit(sample_deck(PNG).to_bytes(), AuditOptions(mode="rules_only"))
    assert report.meta.kind == "pptx"
    assert {f.severity.value for f in report.findings} == {"critical", "high", "medium", "low"}
    assert all(f.location.slide for f in report.findings if f.rule_id.startswith("SLD-"))
    assert report.score < 90


def test_the_bundled_sample_deck_matches_the_generator() -> None:
    root = Path(__file__).resolve().parents[2]
    bundled = (root / "ui" / "samples" / "sample-team-update.pptx").read_bytes()
    assert bundled == sample_deck(PNG).to_bytes()
