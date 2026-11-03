"""A fake chat model: unit and integration tests never call a real LLM."""

import re
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage

from accesslens.llm.cache import RateLimiters
from accesslens.llm.provider import Provider
from accesslens.llm.schemas import BatchResult, ItemResult

_TAG = re.compile(r'<document_item id="([^"]+)" rule="([^"]+)">')

Responder = Callable[[list[Any], int], Any]


def message_text(messages: list[Any]) -> str:
    """The human message's text, whether it is a string or a list of content blocks."""
    content = messages[-1].content
    if isinstance(content, str):
        return content
    return "\n".join(b["text"] for b in content if b.get("type") == "text")


def image_blocks(messages: list[Any]) -> list[Any]:
    content = messages[-1].content
    if isinstance(content, str):
        return []
    return [b for b in content if b.get("type") == "image_url"]


def echo(
    *, issue: bool = True, confidence: float = 0.9, suggestion: str = "A better version."
) -> Responder:
    """Answer every item in the prompt with the same verdict."""

    def respond(messages: list[Any], call: int) -> BatchResult:
        return BatchResult(
            results=[
                ItemResult(
                    item_id=item_id,
                    rule_id=rule_id,  # type: ignore[arg-type]
                    issue=issue,
                    confidence=confidence,
                    message="Something is wrong." if issue else "",
                    suggestion=suggestion if issue else "",
                )
                for item_id, rule_id in _TAG.findall(message_text(messages))
            ]
        )

    return respond


class FakeStructured:
    def __init__(self, model: "FakeChatModel", include_raw: bool) -> None:
        self._model = model
        self._include_raw = include_raw

    def invoke(self, messages: list[Any]) -> Any:
        model = self._model
        model.calls.append(messages)
        outcome = model.responder(messages, len(model.calls) - 1)
        if isinstance(outcome, Exception):
            raise outcome
        if not self._include_raw:
            return outcome
        if isinstance(outcome, dict):
            return outcome  # the test supplied a ready-made raw/parsed/parsing_error dict
        usage = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
        return {
            "raw": AIMessage(content="", usage_metadata=usage),  # type: ignore[arg-type]
            "parsed": outcome,
            "parsing_error": None,
        }


class FakeChatModel:
    def __init__(self, responder: Responder) -> None:
        self.responder = responder
        self.calls: list[list[Any]] = []

    def with_structured_output(self, schema: Any, *, include_raw: bool = False) -> FakeStructured:
        return FakeStructured(self, include_raw)


class StatusError(Exception):
    """Looks like a provider HTTP error (429, 503...)."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


def provider(
    responder: Responder, *, name: str = "primary", vision: bool = True
) -> tuple[Provider, FakeChatModel]:
    model = FakeChatModel(responder)
    return Provider(name, f"fake-{name}", vision, lambda: model), model


def no_wait_limiters() -> RateLimiters:
    return RateLimiters(10**6, clock=lambda: 0.0, sleep=lambda _: None)


def service_for(settings: Any, responder: Responder | None = None) -> Any:
    """An AuditService with in-process parsing and a fake LLM (fast, no subprocess)."""
    from accesslens.ingest.parse_docx import extract_image_blobs, parse_docx
    from accesslens.llm.checks import LlmChecker
    from accesslens.service import AuditService

    fake, _ = provider(responder or echo(issue=False))
    checker = LlmChecker([fake], settings, limiters=no_wait_limiters(), sleep=lambda _: None)
    return AuditService(
        settings,
        checker=checker,
        parse=lambda data, s: parse_docx(data),
        extract_images=lambda data, s: extract_image_blobs(data),
    )
