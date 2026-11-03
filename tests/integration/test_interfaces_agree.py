"""Phase 6 definition of done: CLI, API, MCP and UI return identical findings for one file."""

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from client import AccessLensClient
from fastapi.testclient import TestClient

from accesslens.api.auth import hash_key
from accesslens.api.main import create_app
from accesslens.cli import main as cli_main
from accesslens.config import Settings
from accesslens.mcp_server.server import TOP_FINDINGS, create_server
from accesslens.models import AuditOptions
from fakes import service_for

DOCUMENTS = [
    "synthetic/syn-01",
    "synthetic/syn-07",
    "synthetic/syn-16",
    "synthetic/syn-25",
    "clean/clean-01",
    "injection/inj-03",
]
KEY = "agree-key"


def view(findings: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        (f["rule_id"], f["location"]["block_order"], f["severity"], f["message"]) for f in findings
    ]


@pytest.mark.parametrize("name", DOCUMENTS)
def test_every_interface_reports_the_same_findings(
    name: str, corpus: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = corpus[0] / f"{name}.docx"
    data = source.read_bytes()

    cfg = Settings(
        _env_file=None,
        api_keys_sha256=hash_key(KEY),
        rate_limit="1000/minute",
        mcp_allowed_dir=str(tmp_path),
    )
    service = service_for(cfg)
    expected = view(
        service.audit(data, AuditOptions(mode="rules_only")).model_dump(mode="json")["findings"]
    )

    # CLI: the real default wiring, parsing in the subprocess sandbox.
    capsys.readouterr()
    cli_main(["audit", str(source), "--rules-only"])
    cli_report = json.loads(capsys.readouterr().out)
    assert view(cli_report["findings"]) == expected

    # REST API.
    api = TestClient(create_app(service, cfg))
    response = api.post(
        "/v1/audits",
        files={"file": ("x.docx", data)},
        data={"mode": "rules_only"},
        headers={"X-API-Key": KEY},
    )
    assert view(response.json()["findings"]) == expected

    # UI client, which talks to the same API.
    ui_report = AccessLensClient("http://testserver", KEY, http=api).audit(data, rules_only=True)
    assert view(ui_report["findings"]) == expected

    # MCP tool: top findings, same order, same rules and blocks.
    shutil.copy(source, tmp_path / "doc.docx")
    server = create_server(cfg, service)
    result = asyncio.run(server.call_tool("audit_docx", {"path": "doc.docx", "rules_only": True}))
    mcp = json.loads(result.content[0].text)
    shown = expected[:TOP_FINDINGS]
    assert [
        (f["rule_id"], f["block"], f["severity"], f["problem"]) for f in mcp["findings"]
    ] == shown
    assert mcp["score"] == cli_report["score"] == response.json()["score"]
