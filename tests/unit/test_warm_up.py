import nltk
import pytest

from accesslens.rules.text import warm_up


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    warm_up.cache_clear()


def test_production_refuses_to_start_without_the_dictionary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(*args: object, **kwargs: object) -> None:
        raise LookupError("cmudict not found")

    monkeypatch.setattr(nltk.data, "find", missing)
    with pytest.raises(RuntimeError, match="never downloads"):
        warm_up(allow_download=False)


def test_production_never_triggers_a_download_when_the_dictionary_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    downloads: list[object] = []
    monkeypatch.setattr(nltk, "download", lambda *a, **k: downloads.append(a))
    warm_up(allow_download=True)  # makes sure the dictionary is present locally
    warm_up.cache_clear()
    warm_up(allow_download=False)
    assert downloads == []
