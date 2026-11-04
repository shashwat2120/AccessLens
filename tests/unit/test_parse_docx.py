import csv
from pathlib import Path

from accesslens.ingest.parse_docx import parse_docx
from accesslens.ingest.validate import validate_docx
from accesslens.models import ParsedDocument


def load(corpus: tuple[Path, Path], folder: str, doc_id: str) -> ParsedDocument:
    data = (corpus[0] / folder / f"{doc_id}.docx").read_bytes()
    validate_docx(data)
    return parse_docx(data)


def test_every_corpus_document_parses(corpus: tuple[Path, Path]) -> None:
    paths = sorted(corpus[0].rglob("*.docx"))
    assert len(paths) == 40
    for path in paths:
        data = path.read_bytes()
        assert validate_docx(data) == parse_docx(data).meta.sha256


def test_clean_document_structure(corpus: tuple[Path, Path]) -> None:
    doc = load(corpus, "clean", "clean-01")
    assert doc.meta.title == "Clean control document 1"
    assert doc.meta.language == "en-US"
    assert [b.heading_level for b in doc.blocks if b.type == "heading"][:2] == [1, 2]
    assert sum(b.type == "list_item" for b in doc.blocks) == 3
    assert len(doc.images) == 1
    assert doc.images[0].alt_text
    assert doc.images[0].inline
    assert doc.tables[0].has_header_row
    assert doc.links[0].external
    assert doc.links[0].url == "https://example.org/guidelines"


def test_decorative_image_is_flagged(corpus: tuple[Path, Path]) -> None:
    image = load(corpus, "clean", "clean-04").images[0]
    assert image.decorative
    assert not image.alt_text


def test_document_level_properties(corpus: tuple[Path, Path]) -> None:
    assert load(corpus, "synthetic", "syn-10").meta.title is None
    assert load(corpus, "synthetic", "syn-13").meta.language is None


def test_floating_image_is_not_inline(corpus: tuple[Path, Path]) -> None:
    for doc_id in ("syn-04", "syn-05", "syn-06"):
        images = load(corpus, "synthetic", doc_id).images
        assert sum(not i.inline for i in images) == 1


def test_metadata_never_includes_author(corpus: tuple[Path, Path]) -> None:
    dumped = load(corpus, "clean", "clean-01").meta.model_dump_json()
    assert "AccessLens corpus" not in dumped


def test_parser_agrees_with_answer_key_block_order(corpus: tuple[Path, Path]) -> None:
    """Every planted issue sits at the block the key says, with the expected structure."""
    with corpus[1].open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    folders = {"syn": "synthetic", "clean": "clean", "inj": "injection"}
    checked = 0
    for row in rows:
        doc_id, rule = row["doc_id"], row["rule_id"]
        if doc_id.split("-")[1].startswith("p"):
            continue  # decks are parsed by test_pptx
        doc = load(corpus, folders[doc_id.split("-")[0]], doc_id)
        order = int(row["block_order"])
        block = doc.blocks[order]
        runs = block.runs
        if rule in {"IMG-001", "IMG-002", "IMG-003", "IMG-004", "IMG-005"}:
            assert any(i.block_id == block.id for i in doc.images), (doc_id, rule)
        elif rule.startswith("TBL-"):
            table = next(t for t in doc.tables if t.block_id == block.id)
            if rule == "TBL-001":
                assert not table.has_header_row
            if rule == "TBL-002":
                assert table.has_merged_cells
            if rule == "TBL-003":
                assert table.empty_cell_ratio > 0.5
        elif rule == "HDG-004":
            assert block.type == "heading"
            assert not block.text
        elif rule == "HDG-002":
            assert block.heading_level == 4
        elif rule == "HDG-003":
            assert block.type == "paragraph"
            assert runs
            assert all(r.bold for r in runs)
        elif rule in {"LNK-001", "LNK-002", "LNK-003"}:
            assert any(link.block_id == block.id for link in doc.links), (doc_id, rule)
        elif rule == "LST-001":
            assert block.text.startswith(("- ", "• ", "1. "))
        elif rule == "CLR-001":
            assert any(r.color_hex for r in runs)
        elif rule == "TXT-004":
            assert any(r.underline for r in runs)
        elif rule == "TXT-005":
            assert any(r.size_pt == 8 for r in runs)
        else:
            continue
        checked += 1
    assert checked > 60
