"""Parse in a child process with a wall-clock timeout and memory limit (SECURITY §4).

The document goes to the child over stdin, so no work file (and no filename) ever exists.
The memory limit uses ``resource.setrlimit`` and is therefore enforced on POSIX only; the
timeout applies everywhere.
"""

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


def parse_in_sandbox(data: bytes, settings: Settings | None = None) -> ParsedDocument:
    """Validate and parse ``data`` in a subprocess; any failure becomes ``ParseFailedError``."""
    cfg = settings or get_settings()
    command = [
        sys.executable,
        "-I",
        "-m",
        "accesslens.ingest.worker",
        str(cfg.parse_memory_mb),
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
    try:
        return ParsedDocument.model_validate_json(result.stdout)
    except ValidationError as exc:
        raise ParseFailedError from exc
