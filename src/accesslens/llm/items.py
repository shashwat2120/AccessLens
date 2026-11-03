"""Choose which parts of a document the LLM should review, and prepare them safely.

Every string that leaves this module is redacted (if enabled), length-capped and, when put in a
prompt, escaped. Images are sent only when they are a supported format and under the size cap.
"""

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from accesslens.config import Settings
from accesslens.llm.redact import redact
from accesslens.models import Block, Finding, ParsedDocument

_ACRONYM = re.compile(r"\b[A-Z]{2,6}s?\b")
_MAX_ITEMS = 200
_MIME_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)
# Fewer false alarms: abbreviations nearly every reader knows.
_COMMON_ACRONYMS = {"USA", "UK", "EU", "UN", "PDF", "FAQ", "TV", "ID", "AM", "PM", "OK", "CEO"}
# LLM review priority; batches are formed per rule so each prompt has a single task.
RULE_ORDER = ("IMG-003", "LNK-003", "TXT-006", "TXT-001", "TXT-002")


@dataclass(frozen=True)
class LlmItem:
    id: str
    rule_id: str
    block_id: str
    text: str  # already redacted and capped, not yet escaped
    image: bytes | None = None
    image_mime: str | None = None
    image_sha256: str | None = None
    target_finding_id: str | None = None  # rewrites attach to an existing rule finding

    @property
    def content_hash(self) -> str:
        digest = hashlib.sha256(self.text.encode("utf-8"))
        digest.update((self.image_sha256 or "").encode("utf-8"))
        return digest.hexdigest()


def sniff_image_mime(data: bytes) -> str | None:
    for signature, mime in _MIME_SIGNATURES:
        if data.startswith(signature):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _prepare(text: str, settings: Settings) -> str:
    text = " ".join(text.split())
    text = redact(text) if settings.pii_redaction else text
    return text[: settings.llm_max_item_chars]


def _destination(url: str | None, settings: Settings) -> str:
    """Host and path only; query strings and fragments can carry tokens or personal data."""
    if not url:
        return "(internal link)"
    parts = urlsplit(url)
    return _prepare(f"{parts.scheme}://{parts.netloc}{parts.path}", settings)


def select_items(
    doc: ParsedDocument,
    rule_findings: list[Finding],
    image_blobs: dict[str, bytes],
    settings: Settings,
) -> tuple[list[LlmItem], list[str]]:
    """Build review items in priority order; returns (items, warnings)."""
    flagged: dict[str, set[str]] = {}
    for finding in rule_findings:
        flagged.setdefault(finding.location.block_id, set()).add(finding.rule_id)
    blocks: dict[str, Block] = {b.id: b for b in doc.blocks}
    items: list[LlmItem] = []
    warnings: list[str] = []
    seen: set[tuple[str, str]] = set()

    def add(item: LlmItem) -> None:
        key = (item.rule_id, item.content_hash)
        if key not in seen and len(items) < _MAX_ITEMS:
            seen.add(key)
            items.append(item)

    skipped_images = 0
    for image in doc.images:
        alt = (image.alt_text or "").strip()
        if image.decorative or not alt:
            continue
        if flagged.get(image.block_id, set()) & {"IMG-001", "IMG-002"}:
            continue
        blob = image_blobs.get(image.id)
        mime = sniff_image_mime(blob) if blob else None
        too_big = blob is not None and len(blob) > settings.llm_max_image_mb * 1024 * 1024
        text = _prepare(
            f"Alt text: {alt}\n"
            f"Text before: {image.context_before}\nText after: {image.context_after}",
            settings,
        )
        if blob and mime and not too_big:
            add(
                LlmItem(
                    f"item-{len(items):03d}",
                    "IMG-003",
                    image.block_id,
                    text,
                    blob,
                    mime,
                    image.image_sha256,
                )
            )
        else:
            skipped_images += 1
            # Text-only review is still possible; the checker lowers confidence for it.
            add(LlmItem(f"item-{len(items):03d}", "IMG-003", image.block_id, text))
    if skipped_images:
        warnings.append(
            f"{skipped_images} image(s) could not be sent for visual review "
            "(unsupported format, too large, or linked); alt text was reviewed without the image."
        )

    destinations: dict[str, set[str]] = {}
    for link in doc.links:
        destinations.setdefault(link.text.strip().lower(), set()).add(link.url or "")
    for link in doc.links:
        block = blocks.get(link.block_id)
        if block is None or flagged.get(link.block_id, set()) & {"LNK-001", "LNK-002"}:
            continue
        shared = len(destinations[link.text.strip().lower()])
        note = (
            f"\nThe same link text is used for {shared} different destinations."
            if shared > 1
            else ""
        )
        text = _prepare(
            f"Link text: {link.text}\nDestination: {_destination(link.url, settings)}\n"
            f"Sentence: {block.text}{note}",
            settings,
        )
        add(LlmItem(f"item-{len(items):03d}", "LNK-003", link.block_id, text))

    for block in doc.blocks:
        if block.type not in ("paragraph", "list_item"):
            continue
        terms = {t for t in _ACRONYM.findall(block.text) if t.rstrip("s") not in _COMMON_ACRONYMS}
        undefined = {t for t in terms if f"({t})" not in block.text}
        if undefined:
            add(
                LlmItem(
                    f"item-{len(items):03d}", "TXT-006", block.id, _prepare(block.text, settings)
                )
            )

    for finding in rule_findings:
        if finding.rule_id in ("TXT-001", "TXT-002") and finding.location.block_id in blocks:
            block = blocks[finding.location.block_id]
            add(
                LlmItem(
                    f"item-{len(items):03d}",
                    finding.rule_id,
                    block.id,
                    _prepare(block.text, settings),
                    target_finding_id=finding.id,
                )
            )

    items.sort(key=lambda i: RULE_ORDER.index(i.rule_id))
    return items, warnings
