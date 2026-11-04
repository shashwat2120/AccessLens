"""Ten concurrent rules-only audits through the real sandbox must all succeed (Phase 7)."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from load_test import percentile, run_load

from accesslens.api.auth import hash_key
from accesslens.api.main import create_app
from accesslens.config import Settings
from accesslens.service import AuditService

KEY = "load-key"


def test_ten_concurrent_rules_only_audits_all_succeed(corpus: tuple[Path, Path]) -> None:
    cfg = Settings(_env_file=None, api_keys_sha256=hash_key(KEY), rate_limit="1000/minute")
    client = TestClient(create_app(AuditService(cfg), cfg))  # default wiring: real sandbox
    data = (corpus[0] / "synthetic" / "syn-01.docx").read_bytes()

    def send(payload: bytes) -> Any:
        return client.post(
            "/v1/audits",
            files={"file": ("document.docx", payload)},
            data={"mode": "rules_only"},
            headers={"X-API-Key": KEY},
        )

    result = run_load(send, data, concurrency=10, requests=20)
    assert result["failed"] == 0, result
    assert result["succeeded"] == 20
    # A loose sanity bound for slow CI machines; the real p95 <= 3 s check runs against the
    # deployed service with `python eval/load_test.py`.
    assert result["p95_s"] < 30, result


def test_percentile_helper() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert percentile(values, 50) in (5.0, 6.0)
    assert percentile(values, 95) == 10.0
    assert percentile([2.5], 95) == 2.5
