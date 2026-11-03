"""JSON logging for the whole process (docs/07-ENGINEERING-STANDARDS.md, Observability).

Logs carry ids, hashes, sizes, durations and counts only; never document text, alt text,
filenames or image bytes (SECURITY §6). Standard-library loggers used elsewhere in the code
are rendered through the same JSON pipeline.
"""

import logging
import sys
from typing import Any

import structlog

_SHARED: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
]


def configure_logging(level: int = logging.INFO) -> None:
    """Route structlog and stdlib logging to stderr as one JSON object per line."""
    structlog.configure(
        processors=[*_SHARED, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=_SHARED,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def get_logger() -> Any:
    return structlog.get_logger("accesslens")
