"""Parse in a child process with a wall-clock timeout and memory limit (SECURITY §4).

The document goes to the child over stdin, so no work file (and no filename) ever exists.
The memory limit uses ``resource.setrlimit`` and is therefore enforced on POSIX only; the
timeout applies everywhere.
"""

import base64
import binascii
import json
import os

# Fixed argv, no shell; document bytes go to the child over stdin only.
import subprocess  # nosec B404
import sys

from pydantic import ValidationError

from accesslens.config import Settings, get_settings
from accesslens.errors import ParseFailedError
from accesslens.models import ParsedDocument

_KEEP_ENV = ("PATH", "SYSTEMROOT", "TEMP", "TMP")


def _child_env() -> dict[str, str]:
    """Pass the child almost nothing, in particular no API keys."""
    return {key: os.environ[key] for key in _KEEP_ENV if key in os.environ}


def _run_worker(data: bytes, cfg: Settings, *extra: str) -> bytes:
    command = [
        sys.executable,
        "-I",
        "-m",
        "accesslens.ingest.worker",
        str(cfg.parse_memory_mb),
        *extra,
    ]
    try:
        result = subprocess.run(  # noqa: S603  # nosec B603
            command,
            input=data,
            capture_output=True,
            timeout=cfg.parse_timeout_s,
            check=False,
            env=_child_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ParseFailedError from exc
    if result.returncode != 0:
        raise ParseFailedError
    return result.stdout


def parse_in_sandbox(data: bytes, settings: Settings | None = None) -> ParsedDocument:
    """Validate and parse ``data`` in a subprocess; any failure becomes ``ParseFailedError``."""
    output = _run_worker(data, settings or get_settings(), "parse")
    try:
        return ParsedDocument.model_validate_json(output)
    except ValidationError as exc:
        raise ParseFailedError from exc


def extract_images_in_sandbox(data: bytes, settings: Settings | None = None) -> dict[str, bytes]:
    """Embedded image bytes by ``ImageInfo.id``, extracted in the sandbox.

    Images over ``LLM_MAX_IMAGE_MB`` are left out here, so they are never sent to the parent.
    """
    cfg = settings or get_settings()
    output = _run_worker(data, cfg, "images", str(cfg.llm_max_image_mb * 1024 * 1024))
    try:
        encoded = json.loads(output)
        return {key: base64.b64decode(value, validate=True) for key, value in encoded.items()}
    except (ValueError, TypeError, AttributeError, binascii.Error) as exc:
        raise ParseFailedError from exc
