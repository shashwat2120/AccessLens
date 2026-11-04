import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from client import AccessLensClient, ApiError
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from accesslens.api.auth import hash_key
from accesslens.api.main import create_app
from accesslens.config import Settings
from fakes import service_for

ROOT = Path(__file__).resolve().parents[2]
KEY = "ui-key"


@pytest.fixture
def api() -> TestClient:
    cfg = Settings(_env_file=None, api_keys_sha256=hash_key(KEY), rate_limit="1000/minute")
    return TestClient(create_app(service_for(cfg), cfg))


def test_client_gets_json_html_and_xlsx(api: TestClient, corpus: tuple[Path, Path]) -> None:
    data = (corpus[0] / "synthetic" / "syn-01.docx").read_bytes()
    client = AccessLensClient("http://testserver", KEY, http=api)
    report = client.audit(data, rules_only=True)
    assert report["mode"] == "rules_only"
    assert report["counts"]["critical"] >= 1
    assert b"<html" in client.audit(data, rules_only=True, fmt="html")
    assert zipfile.is_zipfile(io.BytesIO(client.audit(data, rules_only=True, fmt="xlsx")))


def test_client_turns_api_problems_into_safe_errors(
    api: TestClient, corpus: tuple[Path, Path]
) -> None:
    wrong_key = AccessLensClient("http://testserver", "nope", http=api)
    with pytest.raises(ApiError) as unauthorized:
        wrong_key.audit(b"x", rules_only=True)
    assert unauthorized.value.code == "unauthorized"
    client = AccessLensClient("http://testserver", KEY, http=api)
    with pytest.raises(ApiError) as invalid:
        client.audit(b"not a docx", rules_only=True)
    assert invalid.value.code == "invalid_file"
    assert "Traceback" not in str(invalid.value)


def test_client_never_sends_the_users_file_name(api: TestClient) -> None:
    sent: dict[str, Any] = {}
    original = api.post

    def spy(*args: Any, **kwargs: Any) -> Any:
        sent.update(kwargs["files"])
        return original(*args, **kwargs)

    api.post = spy  # type: ignore[method-assign]
    with pytest.raises(ApiError):
        AccessLensClient("http://testserver", KEY, http=api).audit(b"x", rules_only=True)
    assert sent["file"][0] == "document.docx"


def test_streamlit_page_shows_the_privacy_notice_and_keeps_ai_off_by_default() -> None:
    app = AppTest.from_file(str(ROOT / "ui" / "streamlit_app.py"), default_timeout=30).run()
    assert not app.exception
    page = " ".join(m.value for m in app.markdown)
    assert "Find and fix accessibility problems" in page
    assert "never stored" in page
    assert "Rules only" in page
    assert "confidential" in page
    assert app.toggle[0].value is False  # nothing is sent to an AI service unless chosen
    labels = {b.label: b for b in app.button}
    assert labels["Check accessibility"].disabled  # nothing to check until a file is uploaded
    assert not labels["Try a sample document"].disabled
