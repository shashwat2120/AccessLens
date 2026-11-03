import io
import warnings
import zipfile
from pathlib import Path

import pytest

from accesslens.config import Settings
from accesslens.errors import FileTooLargeError, InvalidFileError, MacroEnabledError
from accesslens.ingest.validate import MAIN_CONTENT_TYPE, validate_docx

MACRO_TYPE = "application/vnd.ms-word.document.macroEnabled.main+xml"
DOCUMENT = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    b"<w:body/></w:document>"
)


def content_types(main: str = MAIN_CONTENT_TYPE) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        f'<Override PartName="/word/document.xml" ContentType="{main}"/></Types>'
    ).encode()


def make_docx(extra: dict[str, bytes] | None = None, *, main: str = MAIN_CONTENT_TYPE) -> bytes:
    entries = {"[Content_Types].xml": content_types(main), "word/document.xml": DOCUMENT}
    entries.update(extra or {})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def settings(**overrides: int) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_minimal_valid_docx_passes() -> None:
    assert len(validate_docx(make_docx())) == 64


def test_generated_corpus_passes(corpus: tuple[Path, Path]) -> None:
    for path in corpus[0].rglob("*.docx"):
        validate_docx(path.read_bytes())


def test_oversize_file_is_rejected() -> None:
    data = b"PK\x03\x04" + bytes(11 * 1024 * 1024)
    with pytest.raises(FileTooLargeError):
        validate_docx(data)


@pytest.mark.parametrize(
    "data",
    [b"MZ\x90\x00" + bytes(100), b"%PDF-1.7\n" + bytes(100), b"", b"PK\x03\x04truncated"],
    ids=["exe", "pdf", "empty", "truncated-zip"],
)
def test_non_docx_is_rejected_by_content(data: bytes) -> None:
    with pytest.raises(InvalidFileError):
        validate_docx(data)


def test_zip_bomb_is_rejected_by_ratio() -> None:
    with pytest.raises(InvalidFileError):
        validate_docx(make_docx({"word/bomb.bin": bytes(5 * 1024 * 1024)}))


def test_total_uncompressed_size_is_capped() -> None:
    data = make_docx({"word/big.bin": bytes(2 * 1024 * 1024)})
    with pytest.raises(InvalidFileError):
        validate_docx(data, settings(max_uncompressed_mb=1, max_compression_ratio=10**9))


def test_entry_count_is_capped() -> None:
    data = make_docx({f"word/media/{i}.bin": b"x" for i in range(10)})
    with pytest.raises(InvalidFileError):
        validate_docx(data, settings(max_zip_entries=5))


@pytest.mark.parametrize("name", ["../evil.xml", "word/../../evil.xml", "/abs.xml", "C:/evil.xml"])
def test_zip_slip_names_are_rejected(name: str) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types())
        archive.writestr(zipfile.ZipInfo(name), b"x")
    with pytest.raises(InvalidFileError):
        validate_docx(buffer.getvalue())


def test_duplicate_entry_names_are_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        archive.writestr("[Content_Types].xml", content_types())
        archive.writestr("word/document.xml", DOCUMENT)
        archive.writestr("word/document.xml", DOCUMENT)
    with pytest.raises(InvalidFileError):
        validate_docx(buffer.getvalue())


BILLION_LAUGHS = (
    b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
    b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
    b'<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>'
    b"<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
    b"&lol3;</w:document>"
)
XXE = (
    b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
    b"<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
    b"&x;</w:document>"
)


@pytest.mark.parametrize(
    "document",
    [
        BILLION_LAUGHS,
        XXE,
        XXE.replace(b"DOCTYPE", b"doctype"),
        XXE.decode().encode("utf-16"),
        XXE.replace(b'<?xml version="1.0"?>', b'<?xml version="1.0" encoding="IBM037"?>'),
    ],
    ids=["billion-laughs", "xxe", "lowercase-doctype", "utf16", "exotic-encoding"],
)
def test_doctype_in_any_xml_part_is_rejected(document: bytes) -> None:
    with pytest.raises(InvalidFileError):
        validate_docx(make_docx({"word/document.xml": document}))


def test_doctype_in_a_non_document_part_is_rejected() -> None:
    with pytest.raises(InvalidFileError):
        validate_docx(make_docx({"word/styles.xml": XXE}))


def test_macro_enabled_content_type_is_rejected() -> None:
    with pytest.raises(MacroEnabledError):
        validate_docx(make_docx(main=MACRO_TYPE))


def test_vba_project_is_rejected_even_with_normal_content_type() -> None:
    with pytest.raises(MacroEnabledError):
        validate_docx(make_docx({"word/vbaProject.bin": b"\xd0\xcf\x11\xe0"}))


def test_wrong_main_part_type_is_rejected() -> None:
    with pytest.raises(InvalidFileError):
        validate_docx(make_docx(main="application/octet-stream"))


def test_missing_content_types_is_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", DOCUMENT)
    with pytest.raises(InvalidFileError):
        validate_docx(buffer.getvalue())
