"""Pipeline nodes: plain functions from state to a partial state update.

No node gets tools or reaches any service other than the ones in ``Deps``. Errors from
``validate`` and ``parse`` propagate as typed errors; the LLM nodes cannot fail an audit.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from accesslens.agent.state import AuditState
from accesslens.config import Settings
from accesslens.ingest.validate import validate_docx
from accesslens.llm.checks import LlmChecker
from accesslens.llm.items import select_items
from accesslens.models import ParsedDocument
from accesslens.report.build import build_report
from accesslens.report.merge import merge_findings
from accesslens.rules import RuleConfig, run_rules

Node = Callable[[AuditState], dict[str, Any]]


@dataclass(frozen=True)
class Deps:
    settings: Settings
    checker: LlmChecker
    parse: Callable[[bytes, Settings], ParsedDocument]
    extract_images: Callable[[bytes, Settings], dict[str, bytes]]


def _timed(name: str, fn: Node) -> Node:
    def wrapper(state: AuditState) -> dict[str, Any]:
        started = time.perf_counter()
        update = fn(state)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        return {**update, "timings": {**state.get("timings", {}), name: elapsed}}

    return wrapper


def make_nodes(deps: Deps) -> dict[str, Node]:
    settings = deps.settings

    def validate(state: AuditState) -> dict[str, Any]:
        return {"sha256": validate_docx(state["file_bytes"], settings)}

    def parse(state: AuditState) -> dict[str, Any]:
        return {"parsed": deps.parse(state["file_bytes"], settings)}

    def rule_checks(state: AuditState) -> dict[str, Any]:
        grade = state["options"].target_grade or settings.target_grade
        findings, warnings = run_rules(state["parsed"], RuleConfig(target_grade=grade))
        return {
            "rule_findings": findings,
            "warnings": [*state.get("warnings", []), *warnings],
        }

    def select_llm_items(state: AuditState) -> dict[str, Any]:
        parsed = state["parsed"]
        blobs = deps.extract_images(state["file_bytes"], settings) if parsed.images else {}
        items, warnings = select_items(parsed, state["rule_findings"], blobs, settings)
        return {"llm_items": items, "warnings": [*state.get("warnings", []), *warnings]}

    def llm_checks(state: AuditState) -> dict[str, Any]:
        outcome = deps.checker.run(state["parsed"], state["llm_items"])
        return {
            "llm_outcome": outcome,
            "warnings": [*state.get("warnings", []), *outcome.warnings],
        }

    def merge(state: AuditState) -> dict[str, Any]:
        outcome = state.get("llm_outcome")
        findings = merge_findings(
            state["rule_findings"],
            outcome.findings if outcome else [],
            outcome.rewrites if outcome else [],
        )
        return {"findings": findings}

    def build(state: AuditState) -> dict[str, Any]:
        outcome = state.get("llm_outcome")
        report = build_report(
            state["parsed"],
            state["findings"],
            mode=state["mode"],
            usage=outcome.usage if outcome else None,
            warnings=state.get("warnings", []),
        )
        return {"report": report}

    steps: dict[str, Node] = {
        "validate": validate,
        "parse": parse,
        "rule_checks": rule_checks,
        "select_llm_items": select_llm_items,
        "llm_checks": llm_checks,
        "merge": merge,
        "build_report": build,
    }
    return {name: _timed(name, fn) for name, fn in steps.items()}
