import io
import socket
import sys
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn

from accesslens.config import Settings
from accesslens.errors import ParseFailedError
from accesslens.ingest import sandbox
from accesslens.ingest.parse_docx import parse_docx
from accesslens.ingest.sandbox import parse_in_sandbox
from accesslens.ingest.validate import validate_docx


def test_sandbox_result_matches_in_process_parse(corpus: tuple[Path, Path]) -> None:
    data = (corpus[0] / "clean" / "clean-01.docx").read_bytes()
    assert parse_in_sandbox(data) == parse_docx(data)


@pytest.mark.parametrize("data", [b"not a docx", b"PK\x03\x04" + bytes(64)])
def test_bad_input_fails_generically(data: bytes) -> None:
    with pytest.raises(ParseFailedError) as excinfo:
        parse_in_sandbox(data)
    assert str(excinfo.value) == ParseFailedError.default_message


def test_timeout_becomes_parse_failed(corpus: tuple[Path, Path]) -> None:
    data = (corpus[0] / "clean" / "clean-01.docx").read_bytes()
    with pytest.raises(ParseFailedError):
        parse_in_sandbox(data, Settings(_env_file=None, parse_timeout_s=0.01))


@pytest.mark.skipif(sys.platform == "win32", reason="RLIMIT_AS exists on POSIX only")
def test_memory_limit_is_enforced_in_the_child(corpus: tuple[Path, Path]) -> None:
    data = (corpus[0] / "clean" / "clean-01.docx").read_bytes()
    assert parse_in_sandbox(data, Settings(_env_file=None, parse_memory_mb=512))
    # The parser alone needs roughly 60 MB of address space, so 32 MB is too little to even
    # import it: the child dies and the failure surfaces as the same generic error as any
    # other parse failure.
    with pytest.raises(ParseFailedError):
        parse_in_sandbox(data, Settings(_env_file=None, parse_memory_mb=32))


def test_child_process_receives_no_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    monkeypatch.setenv("GROQ_API_KEY", "secret")
    assert not {"GEMINI_API_KEY", "GROQ_API_KEY"} & set(sandbox._child_env())


def test_external_relationships_are_recorded_without_network(
    corpus: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = Document(str(corpus[0] / "clean" / "clean-01.docx"))
    rel_id = doc.part.relate_to("http://127.0.0.1:9/tracker.png", RT.IMAGE, is_external=True)
    blip = doc.element.body.xpath(".//a:blip")[0]
    del blip.attrib[qn("r:embed")]
    blip.set(qn("r:link"), rel_id)
    buffer = io.BytesIO()
    doc.save(buffer)

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

    validate_docx(buffer.getvalue())
    parsed = parse_docx(buffer.getvalue())
    assert parsed.images[0].image_sha256 == sandbox_empty_hash()
    assert parsed.links[0].external


def sandbox_empty_hash() -> str:
    import hashlib

    return hashlib.sha256(b"").hexdigest()
