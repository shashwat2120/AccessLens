"""MCP server over stdio (SECURITY §8). No network listener, no HTTP transport.

Tools: ``audit_docx``, ``list_rules``, ``explain_rule``. Tool output is data only: it contains
no instructions to the calling model and snippets are capped at 120 characters. Files are read
only from inside ``MCP_ALLOWED_DIR`` and then go through the same ``AuditService`` as every other
interface, so validation, the sandbox, redaction and the LLM budget all apply.

Run: ``python -m accesslens.mcp_server.server`` (``make run-mcp``).
"""

import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from accesslens.config import Settings, get_settings
from accesslens.errors import AccessLensError, InvalidRequestError
from accesslens.models import AuditOptions, Report
from accesslens.rules.catalog import get_rule, rule_catalog
from accesslens.service import AuditService

TOP_FINDINGS = 25


def resolve_allowed_path(raw: str, allowed_dir: str) -> Path:
    """Return the real path of ``raw`` if it is a .docx inside ``allowed_dir``, else raise.

    ``realpath`` resolves symlinks and ``..`` first, so a link pointing outside the allowed
    folder is rejected just like a plain traversal.
    """
    if not allowed_dir:
        raise InvalidRequestError("No folder is configured for file access.")
    root = Path(os.path.realpath(allowed_dir))
    target = Path(os.path.realpath(root / raw))
    if root != target and root not in target.parents:
        raise InvalidRequestError("That path is outside the allowed folder.")
    if target.suffix.lower() != ".docx" or not target.is_file():
        raise InvalidRequestError("Only existing .docx files can be audited.")
    return target


def summarize(report: Report) -> dict[str, Any]:
    return {
        "score": report.score,
        "mode": report.mode,
        "findings_by_severity": {k.value: v for k, v in report.counts.items()},
        "total_findings": len(report.findings),
        "shown_findings": min(len(report.findings), TOP_FINDINGS),
        "findings": [
            {
                "rule_id": f.rule_id,
                "severity": f.severity.value,
                "block": f.location.block_order,
                "snippet": f.location.snippet[:120],
                "problem": f.message,
                "fix": f.suggestion,
                "source": f.source.value,
            }
            for f in report.findings[:TOP_FINDINGS]
        ],
        "notes": report.warnings,
    }


def create_server(
    settings: Settings | None = None, service: AuditService | None = None
) -> MCPServer:
    cfg = settings or get_settings()
    audit_service = service or AuditService(cfg)
    server = MCPServer("accesslens")

    @server.tool()
    def audit_docx(path: str, rules_only: bool = False) -> dict[str, Any]:
        """Audit a .docx file for accessibility issues; returns a summary and top 25 findings."""
        try:
            target = resolve_allowed_path(path, cfg.mcp_allowed_dir)
            report = audit_service.audit(
                target.read_bytes(),
                AuditOptions(mode="rules_only" if rules_only else "full"),
            )
        except AccessLensError as exc:
            return {"error": exc.code, "message": str(exc)}
        except OSError:
            return {"error": "invalid_file", "message": "The file could not be read."}
        return summarize(report)

    @server.tool()
    def list_rules() -> list[dict[str, Any]]:
        """List every accessibility check: id, title, severity and WCAG criterion."""
        return [
            {
                "id": r.id,
                "title": r.title,
                "severity": r.severity.value,
                "wcag": r.wcag_criterion,
                "source": r.source,
            }
            for r in rule_catalog()
        ]

    @server.tool()
    def explain_rule(rule_id: str) -> dict[str, Any]:
        """Explain one check: what it tests, a WCAG link, and how to fix it."""
        rule = get_rule(rule_id)
        if rule is None:
            return {"error": "invalid_request", "message": "Unknown rule id."}
        return {
            "id": rule.id,
            "title": rule.title,
            "severity": rule.severity.value,
            "wcag_criterion": rule.wcag_criterion,
            "wcag_url": rule.wcag_url,
            "description": rule.description,
            "how_to_fix": rule.how_to_fix,
        }

    return server


def main() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()
