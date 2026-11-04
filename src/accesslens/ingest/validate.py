"""Upload validation, run before any parsing (SECURITY §3).

Nothing is extracted to disk. The zip is inspected in memory, and every XML part is checked
for DOCTYPE declarations so entity expansion and XXE are impossible whatever the parser does.
"""

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from zipfile import ZipInfo

from lxml import etree

from accesslens.errors import (
    AccessLensError,
    FileTooLargeError,
    InvalidFileError,
    MacroEnabledError,
)

if TYPE_CHECKING:
    from accesslens.config import Settings

DocKind = Literal["docx", "pptx"]
MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)
PPTX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"
)
_KIND_BY_MAIN_TYPE: dict[str, DocKind] = {
    MAIN_CONTENT_TYPE.lower(): "docx",
    PPTX_MAIN_CONTENT_TYPE.lower(): "pptx",
}
_MACRO_CONTENT_TYPES = {
    "application/vnd.ms-word.document.macroenabled.main+xml",
    "application/vnd.ms-word.template.macroenabledtemplate.main+xml",
    "application/vnd.ms-powerpoint.presentation.macroenabled.main+xml",
    "application/vnd.ms-powerpoint.slideshow.macroenabled.main+xml",
    "application/vnd.ms-powerpoint.template.macroenabled.main+xml",
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


@dataclass(frozen=True)
class ValidationLimits:
    """The numbers validation needs, without the settings machinery.

    The sandbox child receives these directly so it never imports pydantic-settings, which would
    add about half a second to every audit.
    """

    max_upload_bytes: int
    max_zip_entries: int
    max_uncompressed_bytes: int
    max_compression_ratio: int

    @classmethod
    def from_settings(cls, settings: "Settings") -> "ValidationLimits":
        return cls(
            max_upload_bytes=settings.max_upload_mb * 1024 * 1024,
            max_zip_entries=settings.max_zip_entries,
            max_uncompressed_bytes=settings.max_uncompressed_mb * 1024 * 1024,
            max_compression_ratio=settings.max_compression_ratio,
        )


def validate_docx(
    data: bytes,
    settings: "Settings | None" = None,
    *,
    limits: ValidationLimits | None = None,
) -> str:
    """Raise a typed error unless ``data`` looks like a safe .docx; return its SHA-256."""
    sha, kind = validate_upload(data, settings, limits=limits)
    if kind != "docx":
        raise InvalidFileError
    return sha


def validate_upload(
    data: bytes,
    settings: "Settings | None" = None,
    *,
    limits: ValidationLimits | None = None,
) -> tuple[str, DocKind]:
    """Raise a typed error unless ``data`` is a safe .docx or .pptx; return (SHA-256, kind)."""
    if limits is None:
        from accesslens.config import get_settings

        limits = ValidationLimits.from_settings(settings or get_settings())
    cfg = limits
    if len(data) > cfg.max_upload_bytes:
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
    kind = _check_content_types(content_types)
    return hashlib.sha256(data).hexdigest(), kind


def _check_directory(infos: list[ZipInfo], cfg: ValidationLimits) -> None:
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
        if total > cfg.max_uncompressed_bytes:
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


def _check_content_types(data: bytes) -> DocKind:
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
    kinds = {_KIND_BY_MAIN_TYPE[t] for t in types if t in _KIND_BY_MAIN_TYPE}
    if len(kinds) != 1:  # none, or a file claiming to be both
        raise InvalidFileError
    return kinds.pop()
