"""Config-driven chat model access: primary and fallback providers (TRD §5).

Provider and model names come from settings; nothing is hard-coded. Models are built lazily so
importing this module needs no keys and makes no network calls.
"""

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from accesslens.config import Settings
from accesslens.errors import LlmUnavailableError

SUPPORTED_PROVIDERS = ("gemini", "groq")


def get_chat_model(name: str, model_name: str, settings: Settings) -> Any:
    """Build a deterministic (temperature 0) chat model with no tools bound."""
    if not settings.langsmith_tracing:
        # langsmith is installed transitively; make sure nothing is traced unless enabled.
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
    if name == "gemini":
        key = settings.gemini_api_key
        if not key.get_secret_value():
            raise LlmUnavailableError("The Gemini API key is not configured.")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=key,
            temperature=0,
            timeout=settings.llm_timeout_s,
            max_retries=0,  # retries are ours, so they count against the budget
        )
    if name == "groq":
        key = settings.groq_api_key
        if not key.get_secret_value():
            raise LlmUnavailableError("The Groq API key is not configured.")
        from langchain_groq import ChatGroq

        return ChatGroq(
            model_name=model_name,
            api_key=key,
            temperature=0,
            timeout=settings.llm_timeout_s,
            max_retries=0,
        )
    raise LlmUnavailableError(f"Unsupported LLM provider: {name!r}.")


@dataclass
class Provider:
    """One configured provider; ``model()`` builds the chat model on first use."""

    name: str
    model_name: str
    supports_vision: bool
    factory: Callable[[], Any]
    _model: Any = field(default=None, repr=False)

    def model(self) -> Any:
        if self._model is None:
            self._model = self.factory()
        return self._model


def build_providers(settings: Settings) -> list[Provider]:
    """Primary then fallback; a provider with no model name configured is left out."""
    candidates = (
        (settings.llm_primary, settings.llm_model_primary, settings.llm_primary_supports_vision),
        (settings.llm_fallback, settings.llm_model_fallback, settings.llm_fallback_supports_vision),
    )
    providers: list[Provider] = []
    for name, model_name, vision in candidates:
        if not name or not model_name:
            continue
        providers.append(
            Provider(name, model_name, vision, partial(get_chat_model, name, model_name, settings))
        )
    return providers
