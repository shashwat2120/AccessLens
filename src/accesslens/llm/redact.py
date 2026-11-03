"""PII redaction applied to every string before it can reach an LLM (SECURITY §6).

Emails, phone numbers and long digit runs are replaced by placeholders. This is best effort:
names and free-form identifiers are not detected, which is why the UI also offers rules-only
mode and warns against confidential documents.
"""

import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# International and national formats: optional +, then digits grouped by space, dot, dash or ().
_PHONE = re.compile(r"(?<![\w])\+?\(?\d{1,4}\)?(?:[\s.\-]?\(?\d{2,4}\)?){2,5}(?![\w])")
_LONG_DIGITS = re.compile(r"\d{9,}")
_MIN_PHONE_DIGITS = 7


def _redact_phone(match: re.Match[str]) -> str:
    digits = sum(c.isdigit() for c in match.group(0))
    return "[PHONE]" if digits >= _MIN_PHONE_DIGITS else match.group(0)


def redact(text: str) -> str:
    """Return ``text`` with emails, phone numbers and long digit sequences masked."""
    text = _EMAIL.sub("[EMAIL]", text)
    text = _LONG_DIGITS.sub("[NUMBER]", text)  # before phones, so unbroken digit runs say so
    return _PHONE.sub(_redact_phone, text)
