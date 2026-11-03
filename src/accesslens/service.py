"""The single entry point every interface calls (TRD §1)."""

import time
import uuid
from collections.abc import Callable
from typing import Literal

from accesslens.agent.graph import build_graph
from accesslens.agent.nodes import Deps
from accesslens.agent.state import AuditState
from accesslens.config import Settings, get_settings
from accesslens.errors import AccessLensError
from accesslens.ingest.sandbox import extract_images_in_sandbox, parse_in_sandbox
from accesslens.llm.checks import LlmChecker
from accesslens.llm.provider import Provider, build_providers
from accesslens.logging import get_logger
from accesslens.models import AuditOptions, ParsedDocument, Report

_LLM_DISABLED = "AI review is disabled on this server; showing rule-based results only."


class AuditService:
    """Audit one .docx and return a ``Report``; the API, CLI, MCP server and UI call only this.

    Documents are held in memory for the call and never stored. Logs carry ids, sizes,
    durations and counts, never document content.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        providers: list[Provider] | None = None,
        checker: LlmChecker | None = None,
        parse: Callable[[bytes, Settings], ParsedDocument] = parse_in_sandbox,
        extract_images: Callable[[bytes, Settings], dict[str, bytes]] = extract_images_in_sandbox,
    ) -> None:
        self._settings = settings or get_settings()
        chosen = providers if providers is not None else build_providers(self._settings)
        self._checker = checker or LlmChecker(chosen, self._settings)
        self._graph = build_graph(Deps(self._settings, self._checker, parse, extract_images))
        self._log = get_logger()

    def audit(
        self,
        file_bytes: bytes,
        options: AuditOptions | None = None,
        *,
        request_id: str | None = None,
    ) -> Report:
        """Validate, parse (sandboxed), check, and report.

        Raises a typed ``AccessLensError`` for unusable files; LLM trouble never raises and
        only adds warnings.
        """
        opts = options or AuditOptions()
        request_id = request_id or uuid.uuid4().hex
        mode: Literal["full", "rules_only"] = opts.mode
        warnings: list[str] = []
        if mode == "full" and not self._settings.llm_enabled:
            mode = "rules_only"
            warnings.append(_LLM_DISABLED)

        started = time.perf_counter()
        state: AuditState = {
            "request_id": request_id,
            "file_bytes": file_bytes,
            "options": opts,
            "mode": mode,
            "warnings": warnings,
            "timings": {},
        }
        try:
            result: AuditState = self._graph.invoke(state)
        except AccessLensError as exc:
            self._log.warning(
                "audit_rejected",
                request_id=request_id,
                size_bytes=len(file_bytes),
                error=exc.code,
            )
            raise

        report = result["report"]
        usage = report.llm
        self._log.info(
            "audit_done",
            request_id=request_id,
            file_sha256=report.meta.sha256,
            size_bytes=len(file_bytes),
            mode=report.mode,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            node_ms=result.get("timings", {}),
            findings_by_severity={k.value: v for k, v in report.counts.items()},
            score=report.score,
            llm_calls=usage.calls if usage else 0,
            llm_tokens=(usage.input_tokens + usage.output_tokens) if usage else 0,
            degraded=usage.degraded if usage else False,
            warnings=len(report.warnings),
        )
        return report
