import csv
import re
from collections import Counter
from pathlib import Path

from docx import Document
from generate_corpus import generate

ROOT = Path(__file__).resolve().parents[2]


def read_key(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def catalog_rule_ids() -> set[str]:
    text = (ROOT / "docs" / "04-RULES-CATALOG.md").read_text(encoding="utf-8")
    return set(re.findall(r"^\| ([A-Z]{3}-\d{3}) \|", text, flags=re.MULTILINE))


def test_expected_document_counts(corpus: tuple[Path, Path]) -> None:
    docs, _ = corpus
    assert len(list((docs / "synthetic").glob("*.docx"))) == 30
    assert len(list((docs / "clean").glob("*.docx"))) == 5
    assert len(list((docs / "injection").glob("*.docx"))) == 5


def test_every_document_opens(corpus: tuple[Path, Path]) -> None:
    docs, _ = corpus
    for path in docs.rglob("*.docx"):
        assert Document(str(path)).paragraphs


def test_every_catalog_rule_has_three_planted_instances(corpus: tuple[Path, Path]) -> None:
    _, key = corpus
    counts = Counter(row["rule_id"] for row in read_key(key))
    rule_ids = catalog_rule_ids()
    assert rule_ids, "no rules parsed from the catalog"
    missing = {rule: counts[rule] for rule in rule_ids if counts[rule] < 3}
    assert not missing
    assert set(counts) <= rule_ids


def test_clean_documents_have_no_expected_issues(corpus: tuple[Path, Path]) -> None:
    _, key = corpus
    assert not [row for row in read_key(key) if row["doc_id"].startswith("clean-")]


def test_generation_is_deterministic(tmp_path: Path) -> None:
    generate(tmp_path / "a", tmp_path / "a.csv")
    generate(tmp_path / "b", tmp_path / "b.csv")
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()
