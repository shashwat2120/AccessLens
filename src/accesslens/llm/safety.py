"""Prompt-injection hygiene: escape document text and flag suspicious phrasing (SECURITY §5)."""

import re

_INJECTION = re.compile(
    r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|prompts?)"
    r"|disregard\s+(all\s+)?(the\s+)?(previous|prior|above)"
    r"|(^|\s)(system|assistant)\s*:"
    r"|you\s+are\s+now\b"
    r"|new\s+instructions?\s*:"
    r"|(report|return|respond\s+with|output)\s+(that\s+)?(no|zero|an\s+empty)\s+(issues|findings|list)"
    r"|(report|state|say|claim|confirm)\b[^.]{0,40}\b(no|zero)\s+(accessibility\s+)?"
    r"(issues|problems|findings)"
    r"|fully\s+accessible",
    re.IGNORECASE,
)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def escape_for_item(text: str) -> str:
    """Make document text inert inside ``<document_item>`` tags.

    Angle brackets and ampersands become entities so no document text can open or close a
    tag; control characters are dropped.
    """
    text = _CONTROL.sub(" ", text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def looks_like_injection(text: str) -> bool:
    """Informational only: a match adds a warning, it never blocks or alters an audit."""
    return bool(_INJECTION.search(text))
