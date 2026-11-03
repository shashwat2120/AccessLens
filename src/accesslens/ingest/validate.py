"""Upload validation, run before any parsing (SECURITY §3).

Nothing is extracted to disk. The zip is inspected in memory, and every XML part is checked
for DOCTYPE declarations so entity expansion and XXE are impossible whatever the parser does.
"""

import hashlib
import io
import re
import zipfile
from zipfile import ZipInfo

from lxml import etree

from accesslens.config import Settings, get_settings
from accesslens.errors import (
    AccessLensError,
    FileTooLargeError,
    InvalidFileError,
    MacroEnabledError,
)

MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
_MACRO_CONTENT_TYPES = {
    "application/vnd.ms-word.document.macroenabled.main+xml",
    "application/vnd.ms-word.template.macroenabledtemplate.main+xml",
}
_ZIP_MAGIC = b"PK\x03\x04"
_CONTENT_TYPES = "[Content_Types].xml"
_XML_SUFFIXES = (".xml", ".rels", ".vml")
_ENCODING = re.compile(rb"""^\s*<\?xml[^>]*encoding\s*=\s*["']([^"']+)["']""")
_UTF16_32_BOMS = (b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")
# Tiny entries cannot exhaust memory, and legitimate small XML can compress very well.
_RATIO_FLOOR_BYTES = 4096


def hardened_xml_parser() -> etree.XMLParser:
    """lxml parser that never resolves entities, touches the network, or accepts huge trees."""
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        load_dtd=False,
        dtd_validation=False,
    )


def validate_docx(data: bytes, settings: Settings | None = None) -> str:
    """Raise a typed error unless ``data`` looks like a safe .docx; return its SHA-256."""
    cfg = settings or get_settings()
    if len(data) > cfg.max_upload_mb * 1024 * 1024:
        raise FileTooLargeError
    if not data.startswith(_ZIP_MAGIC):
        raise InvalidFileError

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            _check_directory(infos, cfg)
            content_types: bytes | None = None
            for info in infos:
                if info.is_dir() or not info.filename.lower().endswith(_XML_SUFFIXES):
                    continue
                xml = archive.read(info)
                _check_xml_part(xml)
                if info.filename == _CONTENT_TYPES:
                    content_types = xml
    except AccessLensError:
        raise
    except Exception as exc:  # corrupt zip, bad CRC, unsupported compression, encryption...
        raise InvalidFileError from exc

    if content_types is None:
        raise InvalidFileError
    _check_content_types(content_types)
    return hashlib.sha256(data).hexdigest()


def _check_directory(infos: list[ZipInfo], cfg: Settings) -> None:
    if len(infos) > cfg.max_zip_entries:
        raise InvalidFileError
    seen: set[str] = set()
    total = 0
    for info in infos:
        name = info.filename
        parts = name.replace("\\", "/").split("/")
        if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name) or ".." in parts:
            raise InvalidFileError
        if name.lower() in seen:
            raise InvalidFileError
        seen.add(name.lower())
        if name.lower().endswith("vbaproject.bin"):
            raise MacroEnabledError
        total += info.file_size
        if total > cfg.max_uncompressed_mb * 1024 * 1024:
            raise InvalidFileError
        ratio = info.file_size / max(info.compress_size, 1)
        if info.file_size >= _RATIO_FLOOR_BYTES and ratio > cfg.max_compression_ratio:
            raise InvalidFileError


def _check_xml_part(data: bytes) -> None:
    # A UTF-16/32 or exotic-encoding part would hide "<!DOCTYPE" from a byte search.
    if data.startswith(_UTF16_32_BOMS) or b"\x00" in data[:8]:
        raise InvalidFileError
    declared = _ENCODING.match(data)
    if declared and declared.group(1).lower() not in (b"utf-8", b"utf8"):
        raise InvalidFileError
    if b"<!DOCTYPE" in data.upper():
        raise InvalidFileError


def _check_content_types(data: bytes) -> None:
    try:
        root = etree.fromstring(data, parser=hardened_xml_parser())
    except etree.XMLSyntaxError as exc:
        raise InvalidFileError from exc
    types = {
        (el.get("ContentType") or "").lower()
        for el in root.iter()
        if isinstance(el.tag, str) and el.tag.endswith("}Override")
    }
    if types & _MACRO_CONTENT_TYPES:
        raise MacroEnabledError
    if MAIN_CONTENT_TYPE.lower() not in types:
        raise InvalidFileError
