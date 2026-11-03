"""Versioned prompt templates; the version is recorded in ``Report.llm``."""

from functools import lru_cache
from pathlib import Path

PROMPT_VERSION = "v1"
_DIR = Path(__file__).parent / "prompts"

_TASK_FILES = {
    "IMG-003": "img003",
    "IMG-003-text": "img003_text_only",
    "LNK-003": "lnk003",
    "TXT-006": "txt006",
    "TXT-001": "rewrite",
    "TXT-002": "rewrite",
}


@lru_cache
def _read(stem: str) -> str:
    return (_DIR / f"{stem}_{PROMPT_VERSION}.md").read_text(encoding="utf-8").strip()


def system_prompt() -> str:
    return _read("system")


def task_prompt(rule_id: str, *, text_only: bool = False) -> str:
    key = "IMG-003-text" if rule_id == "IMG-003" and text_only else rule_id
    return _read(_TASK_FILES[key])
