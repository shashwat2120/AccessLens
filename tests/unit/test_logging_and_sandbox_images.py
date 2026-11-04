import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from accesslens.errors import ParseFailedError
from accesslens.ingest.parse_docx import extract_image_blobs
from accesslens.ingest.sandbox import extract_images_in_sandbox
from accesslens.logging import configure_logging, get_logger


@pytest.fixture
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    structlog.reset_defaults()
    root.handlers, root.level = handlers, level


@pytest.mark.usefixtures("restore_logging")
def test_logs_are_one_json_object_per_line(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    get_logger().info("audit_done", request_id="r1", size_bytes=10)
    logging.getLogger("accesslens.llm.checks").info("llm_run items=3 calls=1")
    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert lines[0]["event"] == "audit_done"
    assert lines[0]["request_id"] == "r1"
    assert lines[0]["level"] == "info"
    assert "timestamp" in lines[0]
    assert lines[1]["event"] == "llm_run items=3 calls=1"


@pytest.mark.usefixtures("restore_logging")
def test_the_production_entry_point_turns_on_json_logging(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from accesslens.api import main

    monkeypatch.setattr(main, "create_app", lambda: object())
    main.app_factory()
    get_logger().info("probe", request_id="r1")
    line = capsys.readouterr().err.strip().splitlines()[-1]
    assert json.loads(line)["event"] == "probe"


def test_sandboxed_image_extraction_matches_in_process(corpus: tuple[Path, Path]) -> None:
    data = (corpus[0] / "clean" / "clean-01.docx").read_bytes()
    assert extract_images_in_sandbox(data) == extract_image_blobs(data)


def test_sandboxed_image_extraction_fails_generically_on_bad_input() -> None:
    with pytest.raises(ParseFailedError):
        extract_images_in_sandbox(b"not a docx")
