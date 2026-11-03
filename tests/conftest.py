from pathlib import Path

import pytest
from generate_corpus import generate


@pytest.fixture(scope="session")
def corpus(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """The generated eval corpus and its answer key, built once per test session."""
    base = tmp_path_factory.mktemp("corpus")
    generate(base / "docs", base / "key.csv")
    return base / "docs", base / "key.csv"
