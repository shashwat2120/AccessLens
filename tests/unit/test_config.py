import pytest

from accesslens import __version__
from accesslens.config import Settings


def test_package_has_version() -> None:
    assert __version__


def test_defaults_are_safe() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "dev"
    assert settings.llm_budget_per_doc == 10
    assert settings.max_upload_mb == 10


def test_secrets_are_not_leaked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-value")
    settings = Settings(_env_file=None)
    assert settings.gemini_api_key.get_secret_value() == "super-secret-value"
    assert "super-secret-value" not in repr(settings)
