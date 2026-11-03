"""Property-based fuzzing: mutated input may be rejected, but only with typed errors."""

import io
import zipfile

from docx import Document
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from accesslens.errors import AccessLensError
from accesslens.ingest.parse_docx import parse_docx
from accesslens.ingest.validate import validate_docx


def build_base() -> bytes:
    doc = Document()
    doc.core_properties.title = "Fuzz base"
    doc.add_heading("Heading", 1)
    doc.add_paragraph("Some body text with a few words.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "A"
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


BASE = build_base()
FUZZ = settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def run_pipeline(data: bytes) -> None:
    try:
        validate_docx(data)
        parse_docx(data)
    except AccessLensError:
        pass


def rezip(document_xml: bytes) -> bytes:
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(BASE)) as source,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for info in source.infolist():
            data = document_xml if info.filename == "word/document.xml" else source.read(info)
            target.writestr(info.filename, data)
    return out.getvalue()


def mutate(data: bytes, flips: list[tuple[int, int]], cut: int | None) -> bytes:
    mutable = bytearray(data)
    for index, value in flips:
        mutable[index % len(mutable)] = value
    return bytes(mutable if cut is None else mutable[: cut % (len(mutable) + 1)])


@FUZZ
@given(
    flips=st.lists(st.tuples(st.integers(0, 10**6), st.integers(0, 255)), max_size=20),
    cut=st.one_of(st.none(), st.integers(0, 10**6)),
)
def test_mutated_zip_bytes_only_raise_typed_errors(
    flips: list[tuple[int, int]], cut: int | None
) -> None:
    run_pipeline(mutate(BASE, flips, cut))


@FUZZ
@given(
    flips=st.lists(st.tuples(st.integers(0, 10**6), st.integers(0, 255)), min_size=1, max_size=20),
    cut=st.one_of(st.none(), st.integers(0, 10**6)),
)
def test_mutated_document_xml_only_raises_typed_errors(
    flips: list[tuple[int, int]], cut: int | None
) -> None:
    with zipfile.ZipFile(io.BytesIO(BASE)) as archive:
        xml = archive.read("word/document.xml")
    run_pipeline(rezip(mutate(xml, flips, cut)))
