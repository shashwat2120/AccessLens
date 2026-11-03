"""Run the LLM review: batching, validation, retries, fallback, budget and degraded mode.

Guarantees (SECURITY §5, TRD §5):
- The LLM only ever *adds* findings for IMG-003, LNK-003 and TXT-006, or supplies rewrite
  suggestions for existing TXT-001/TXT-002 findings. It cannot remove or edit any other finding.
- The rule of each answer is fixed by the item we sent; answers naming another rule, an unknown
  item id or a duplicate id are discarded.
- Any failure degrades to "no LLM findings plus a warning"; ``run`` never raises.
"""

import base64
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import sha256
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from accesslens.config import Settings
from accesslens.llm.cache import LruCache, RateLimiters
from accesslens.llm.items import RULE_ORDER, LlmItem
from accesslens.llm.provider import Provider
from accesslens.llm.safety import escape_for_item, looks_like_injection
from accesslens.llm.schemas import BatchResult, ItemResult
from accesslens.llm.templates import PROMPT_VERSION, system_prompt, task_prompt
from accesslens.models import (
    Finding,
    LlmUsage,
    Location,
    ParsedDocument,
    Severity,
    Source,
    WcagLevel,
)
from accesslens.rules.base import snippet_of

logger = logging.getLogger(__name__)

_TEXT_ONLY_PENALTY = 0.2
_REWRITE_RULES = {"TXT-001", "TXT-002"}
_MAX_TEXT = {"message": 300, "suggestion": 500}

# (title, severity, WCAG criterion, level, default message) for the rules the LLM may add.
LLM_RULES: dict[str, tuple[str, Severity, str | None, WcagLevel, str]] = {
    "IMG-003": (
        "Alt text does not describe the image",
        Severity.MEDIUM,
        "1.1.1",
        WcagLevel.A,
        "The alt text may not describe what the image shows.",
    ),
    "LNK-003": (
        "Link text is unclear in context",
        Severity.LOW,
        "2.4.4",
        WcagLevel.A,
        "A reader may not be able to tell where this link goes.",
    ),
    "TXT-006": (
        "Unexplained jargon or abbreviation",
        Severity.LOW,
        "3.1.3",
        WcagLevel.AAA,
        "This text uses terms that may need explaining.",
    ),
}

_DEGRADED = "AI review was only partly available; rule-based results are complete."
_NOT_CONFIGURED = "AI review is not configured; showing rule-based results only."


@dataclass(frozen=True)
class Rewrite:
    """A plain-language rewrite to attach to an existing TXT-001/TXT-002 finding."""

    finding_id: str
    suggestion: str
    confidence: float


@dataclass
class LlmOutcome:
    findings: list[Finding] = field(default_factory=list)
    rewrites: list[Rewrite] = field(default_factory=list)
    usage: LlmUsage | None = None
    warnings: list[str] = field(default_factory=list)


class _InvalidOutput(Exception):
    pass


class _BudgetExhausted(Exception):
    pass


class _ProviderFailed(Exception):
    pass


@lru_cache
def _semaphore(size: int) -> threading.BoundedSemaphore:
    """One process-wide cap on simultaneous LLM calls (free-tier friendly)."""
    return threading.BoundedSemaphore(size)


def _is_transient(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(code, int) and (code == 429 or 500 <= code < 600):
        return True
    name = type(exc).__name__.lower()
    return any(
        marker in name
        for marker in ("ratelimit", "timeout", "unavailable", "resourceexhausted", "deadline")
    )


def _clean(text: str, limit: int) -> str:
    return "".join(c if c.isprintable() or c in "\n\t" else " " for c in text).strip()[:limit]


def apply_rewrites(findings: list[Finding], rewrites: list[Rewrite]) -> list[Finding]:
    """Replace only the suggestion text of matching findings; nothing else can change."""
    by_id = {r.finding_id: r for r in rewrites}
    return [
        f.model_copy(update={"suggestion": by_id[f.id].suggestion}) if f.id in by_id else f
        for f in findings
    ]


class LlmChecker:
    def __init__(
        self,
        providers: list[Provider],
        settings: Settings,
        *,
        cache: LruCache | None = None,
        limiters: RateLimiters | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._providers = providers
        self._settings = settings
        self._cache = cache if cache is not None else LruCache(settings.llm_cache_size)
        self._limiters = limiters or RateLimiters(settings.llm_requests_per_minute)
        self._sleep = sleep

    # -- public ------------------------------------------------------------------------

    def run(self, doc: ParsedDocument, items: list[LlmItem]) -> LlmOutcome:
        """Review ``items``; never raises, always returns what could be established."""
        outcome = LlmOutcome()
        if not self._settings.llm_enabled or not items:
            return outcome
        try:
            return self._run(doc, items)
        except Exception as exc:
            logger.error("llm_run_failed error=%s", type(exc).__name__)
            outcome.warnings.append(_DEGRADED)
            outcome.usage = self._usage(None, 0, 0, 0, degraded=True)
            return outcome

    # -- internals ---------------------------------------------------------------------

    def _run(self, doc: ParsedDocument, items: list[LlmItem]) -> LlmOutcome:
        outcome = LlmOutcome()
        if looks_like_injection(" ".join(i.text for i in items)):
            outcome.warnings.append(
                "Some document text resembles an instruction to an AI system. It was treated "
                "as content, not followed."
            )
        if not self._providers:
            outcome.warnings.append(_NOT_CONFIGURED)
            outcome.usage = self._usage(None, 0, 0, 0, degraded=True)
            return outcome

        state = _State()
        accepted: dict[str, tuple[ItemResult, bool]] = {}
        for rule_id in RULE_ORDER:
            for has_image in (True, False):
                group = [i for i in items if i.rule_id == rule_id and bool(i.image) == has_image]
                for batch in self._batches(group, has_image):
                    self._review(batch, accepted, state)

        reviewed = len(accepted)
        missing = len(items) - reviewed
        if state.budget_hit:
            outcome.warnings.append(f"LLM budget reached; {missing} item(s) not reviewed.")
        elif state.invalid:
            outcome.warnings.append(
                f"AI review returned invalid output for {state.invalid} item(s); "
                "they were not reviewed."
            )
        if state.degraded:
            outcome.warnings.append(_DEGRADED)

        blocks = {b.id: b for b in doc.blocks}
        counts: dict[str, int] = {}
        for item in items:
            entry = accepted.get(item.id)
            if entry is None:
                continue
            result, text_only = entry
            confidence = result.confidence - (
                _TEXT_ONLY_PENALTY if text_only and item.rule_id == "IMG-003" else 0.0
            )
            if not result.issue or confidence < self._settings.llm_min_confidence:
                continue
            if item.rule_id in _REWRITE_RULES:
                suggestion = _clean(result.suggestion, _MAX_TEXT["suggestion"])
                if item.target_finding_id and suggestion:
                    outcome.rewrites.append(
                        Rewrite(item.target_finding_id, suggestion, round(confidence, 2))
                    )
                continue
            block = blocks.get(item.block_id)
            if block is None or item.rule_id not in LLM_RULES:
                continue
            title, severity, criterion, level, default = LLM_RULES[item.rule_id]
            key = f"{item.rule_id}-{block.id}"
            n = counts.get(key, 0)
            counts[key] = n + 1
            outcome.findings.append(
                Finding(
                    id=key if n == 0 else f"{key}-{n}",
                    rule_id=item.rule_id,
                    title=title,
                    severity=severity,
                    wcag_criterion=criterion,
                    wcag_level=level,
                    location=Location(
                        block_id=block.id, block_order=block.order, snippet=snippet_of(block)
                    ),
                    message=_clean(result.message, _MAX_TEXT["message"]) or default,
                    suggestion=_clean(result.suggestion, _MAX_TEXT["suggestion"]),
                    source=Source.LLM,
                    confidence=round(max(confidence, 0.0), 2),
                )
            )
        outcome.usage = self._usage(
            state.last_provider,
            state.calls,
            state.input_tokens,
            state.output_tokens,
            degraded=state.degraded,
        )
        logger.info(
            "llm_run items=%d reviewed=%d calls=%d findings=%d degraded=%s",
            len(items),
            reviewed,
            state.calls,
            len(outcome.findings),
            state.degraded,
        )
        return outcome

    def _batches(self, group: list[LlmItem], has_image: bool) -> list[list[LlmItem]]:
        size = self._settings.llm_vision_batch_size if has_image else self._settings.llm_batch_size
        return [group[i : i + size] for i in range(0, len(group), size)]

    def _key(self, item: LlmItem) -> str:
        model = self._providers[0].model_name
        raw = f"{PROMPT_VERSION}|{item.rule_id}|{bool(item.image)}|{model}|{item.content_hash}"
        return sha256(raw.encode("utf-8")).hexdigest()

    def _review(
        self,
        batch: list[LlmItem],
        accepted: dict[str, tuple[ItemResult, bool]],
        state: "_State",
    ) -> None:
        pending: list[LlmItem] = []
        for item in batch:
            hit = self._cache.get(self._key(item))
            if hit is not None:
                accepted[item.id] = hit
            else:
                pending.append(item)
        if not pending or state.budget_hit:
            return

        for index, provider in enumerate(self._providers):
            use_images = bool(pending[0].image) and provider.supports_vision
            text_only = bool(pending[0].image) and not use_images
            try:
                parsed = self._call_provider(provider, pending, use_images, state)
            except _BudgetExhausted:
                state.budget_hit = True
                return
            except _InvalidOutput:
                state.invalid += len(pending)
                return  # retried once already; the batch is dropped, not sent elsewhere
            except _ProviderFailed:
                state.degraded = True
                continue
            if index > 0:
                state.degraded = True
            state.last_provider = provider
            self._accept(pending, parsed, text_only, accepted)
            return
        state.degraded = True

    def _accept(
        self,
        batch: list[LlmItem],
        parsed: BatchResult,
        text_only: bool,
        accepted: dict[str, tuple[ItemResult, bool]],
    ) -> None:
        by_id = {i.id: i for i in batch}
        for result in parsed.results:
            item = by_id.get(result.item_id)
            if item is None or result.rule_id != item.rule_id or item.id in accepted:
                continue  # unknown id, wrong rule, or duplicate: discard
            accepted[item.id] = (result, text_only)
            self._cache.put(self._key(item), (result, text_only))

    def _call_provider(
        self, provider: Provider, batch: list[LlmItem], use_images: bool, state: "_State"
    ) -> BatchResult:
        messages = self._messages(batch, use_images)
        invalid = 0
        attempt = 0
        while True:
            if state.calls >= self._settings.llm_budget_per_doc:
                raise _BudgetExhausted
            state.calls += 1
            self._limiters.wait(provider.name)
            try:
                with _semaphore(self._settings.llm_concurrency):
                    raw = (
                        provider.model()
                        .with_structured_output(BatchResult, include_raw=True)
                        .invoke(messages)
                    )
                return self._unpack(raw, state)
            except _InvalidOutput:
                invalid += 1
                if invalid >= 2:
                    raise
            except Exception as exc:
                if _is_transient(exc) and attempt < self._settings.llm_max_retries:
                    self._sleep(self._settings.llm_backoff_base_s * 2**attempt)
                    attempt += 1
                    continue
                logger.warning(
                    "llm_provider_error provider=%s error=%s", provider.name, type(exc).__name__
                )
                raise _ProviderFailed from exc

    @staticmethod
    def _unpack(raw: Any, state: "_State") -> BatchResult:
        parsed = raw
        if isinstance(raw, dict):
            message = raw.get("raw")
            usage = getattr(message, "usage_metadata", None) or {}
            state.input_tokens += int(usage.get("input_tokens", 0) or 0)
            state.output_tokens += int(usage.get("output_tokens", 0) or 0)
            if raw.get("parsing_error") is not None:
                raise _InvalidOutput
            parsed = raw.get("parsed")
        try:
            if isinstance(parsed, BatchResult):
                return parsed
            return BatchResult.model_validate(parsed)
        except ValidationError as exc:
            raise _InvalidOutput from exc

    def _messages(self, batch: list[LlmItem], use_images: bool) -> list[Any]:
        rule_id = batch[0].rule_id
        task = task_prompt(rule_id, text_only=rule_id == "IMG-003" and not use_images)
        if rule_id in _REWRITE_RULES:
            task += f"\n\nTarget reading grade: {self._settings.target_grade}."
        if not use_images:
            tags = "\n".join(self._tag(i) for i in batch)
            content: Any = f"{task}\n\nItems:\n{tags}"
        else:
            content = [{"type": "text", "text": f"{task}\n\nItems:"}]
            for item in batch:
                content.append({"type": "text", "text": self._tag(item)})
                if item.image and item.image_mime:
                    encoded = base64.b64encode(item.image).decode("ascii")
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{item.image_mime};base64,{encoded}"},
                        }
                    )
        return [SystemMessage(content=system_prompt()), HumanMessage(content=content)]

    @staticmethod
    def _tag(item: LlmItem) -> str:
        return (
            f'<document_item id="{item.id}" rule="{item.rule_id}">\n'
            f"{escape_for_item(item.text)}\n</document_item>"
        )

    def _usage(
        self,
        provider: Provider | None,
        calls: int,
        input_tokens: int,
        output_tokens: int,
        *,
        degraded: bool,
    ) -> LlmUsage:
        shown = provider or (self._providers[0] if self._providers else None)
        return LlmUsage(
            provider=shown.name if shown else "none",
            model=shown.model_name if shown else "none",
            prompt_version=PROMPT_VERSION,
            calls=calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            degraded=degraded,
        )


@dataclass
class _State:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    invalid: int = 0
    degraded: bool = False
    budget_hit: bool = False
    last_provider: Provider | None = None
