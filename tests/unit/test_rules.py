"""One passing and one failing fixture per rule (docs/04-RULES-CATALOG.md)."""

import pytest

from accesslens.models import ParsedDocument, Run
from accesslens.rules import run_rules
from factories import block, doc, heading, image, link, table

DENSE = (
    "Notwithstanding preceding provisions, organizational stakeholders must demonstrate "
    "comprehensive accountability regarding interdepartmental communication requirements. "
    "Implementation of the aforementioned methodology necessitates substantial coordination "
    "between administrative departments and independent regulatory authorities. Employees "
    "are responsible for acknowledging contractual obligations and maintaining confidentiality."
)
SIMPLE = (
    "The team meets every Monday morning to plan the week. Our office is open from nine to "
    "five on weekdays. Each new member gets a short guide on the first day. Please keep the "
    "shared kitchen clean and tidy."
)


def img_doc(**kw: object) -> ParsedDocument:
    return doc([heading(0, "Report"), block(1, "", "image")], images=[image(1, **kw)])


def link_doc(text: str) -> ParsedDocument:
    return doc([heading(0, "Report"), block(1, "See the page.")], links=[link(1, text)])


def runs_doc(text: str, run: Run, type: str = "paragraph") -> ParsedDocument:
    return doc([heading(0, "Report"), block(1, text, type, runs=[run])])


def text_doc(text: str) -> ParsedDocument:
    return doc([heading(0, "Report"), block(1, text)])


def bold(text: str, **kw: object) -> Run:
    return Run(text=text, bold=True, **kw)  # type: ignore[arg-type]


# (rule id, label, document, expected block orders)
CASES: list[tuple[str, str, ParsedDocument, list[int]]] = [
    ("IMG-001", "fail-none", img_doc(alt_text=None), [1]),
    ("IMG-001", "fail-blank", img_doc(alt_text="   "), [1]),
    ("IMG-001", "pass-alt", img_doc(), []),
    ("IMG-001", "pass-decorative", img_doc(alt_text=None, decorative=True), []),
    ("IMG-002", "fail-word", img_doc(alt_text="image"), [1]),
    ("IMG-002", "fail-word-case", img_doc(alt_text="Photo"), [1]),
    ("IMG-002", "fail-filename", img_doc(alt_text="chart.png"), [1]),
    ("IMG-002", "fail-short", img_doc(alt_text="pic"), [1]),
    ("IMG-002", "pass-descriptive", img_doc(), []),
    ("IMG-002", "pass-decorative", img_doc(alt_text="image", decorative=True), []),
    ("IMG-002", "pass-empty-is-img001", img_doc(alt_text=""), []),
    ("IMG-004", "fail", img_doc(alt_text="word " * 60), [1]),
    ("IMG-004", "pass-at-limit", img_doc(alt_text="a" * 250), []),
    ("IMG-005", "fail-floating", img_doc(inline=False), [1]),
    ("IMG-005", "pass-inline", img_doc(), []),
    ("HDG-001", "fail", doc([block(0, "text " * 350)], word_count=350), [0]),
    ("HDG-001", "pass-has-heading", doc([heading(0, "Hi"), block(1, "text")], word_count=350), []),
    ("HDG-001", "pass-short", doc([block(0, "text")], word_count=100), []),
    ("HDG-002", "fail", doc([heading(0, "A", 1), heading(1, "B", 3)]), [1]),
    (
        "HDG-002",
        "pass-sequential",
        doc([heading(0, "A", 1), heading(1, "B", 2), heading(2, "C", 3)]),
        [],
    ),
    (
        "HDG-002",
        "pass-going-up",
        doc([heading(0, "A", 1), heading(1, "B", 2), heading(2, "C", 1)]),
        [],
    ),
    (
        "HDG-003",
        "fail-bold",
        doc(
            [
                heading(0, "A"),
                block(1, "Key findings", runs=[bold("Key findings")]),
                block(2, "Body text here."),
            ]
        ),
        [1],
    ),
    (
        "HDG-003",
        "fail-large",
        doc(
            [
                heading(0, "A"),
                block(1, "Overview", runs=[Run(text="Overview", size_pt=16)]),
                block(2, "Body text here."),
            ]
        ),
        [1],
    ),
    (
        "HDG-003",
        "pass-followed-by-heading",
        doc([heading(0, "A"), block(1, "Notes", runs=[bold("Notes")]), heading(2, "B", 2)]),
        [],
    ),
    (
        "HDG-003",
        "pass-long-bold",
        doc(
            [heading(0, "A"), block(1, "word " * 20, runs=[bold("word " * 20)]), block(2, "Body.")]
        ),
        [],
    ),
    (
        "HDG-003",
        "pass-last-block",
        doc([heading(0, "A"), block(1, "Notes", runs=[bold("Notes")])]),
        [],
    ),
    ("HDG-004", "fail", doc([heading(0, "A"), heading(1, "", 2)]), [1]),
    ("HDG-004", "pass", doc([heading(0, "A"), heading(1, "B", 2)]), []),
    ("HDG-005", "fail-starts-with-text", doc([block(0, "Intro text"), heading(1, "A")]), [0]),
    ("HDG-005", "fail-starts-with-h2", doc([heading(0, "A", 2), block(1, "x")]), [0]),
    ("HDG-005", "fail-second-h1", doc([heading(0, "A"), block(1, "x"), heading(2, "B", 1)]), [2]),
    ("HDG-005", "pass-title", doc([block(0, "My title", "title"), heading(1, "A", 2)]), []),
    ("HDG-005", "pass-h1", doc([heading(0, "A"), heading(1, "B", 2)]), []),
    ("DOC-001", "fail-none", doc([block(0, "x")], title=None), [0]),
    ("DOC-001", "fail-blank", doc([block(0, "x")], title="  "), [0]),
    ("DOC-001", "pass", doc([block(0, "x")]), []),
    ("DOC-002", "fail", doc([block(0, "x")], language=None), [0]),
    ("DOC-002", "pass", doc([block(0, "x")]), []),
    ("LNK-001", "fail-click-here", link_doc("click here"), [1]),
    ("LNK-001", "fail-punctuation-case", link_doc("Read More."), [1]),
    ("LNK-001", "pass", link_doc("accessibility guidelines"), []),
    ("LNK-002", "fail-https", link_doc("https://example.org/a"), [1]),
    ("LNK-002", "fail-www", link_doc("www.example.org"), [1]),
    ("LNK-002", "pass", link_doc("accessibility guidelines"), []),
    (
        "TBL-001",
        "fail",
        doc([heading(0, "A"), block(1, "", "table")], tables=[table(1, has_header_row=False)]),
        [1],
    ),
    (
        "TBL-001",
        "pass-header",
        doc([heading(0, "A"), block(1, "", "table")], tables=[table(1)]),
        [],
    ),
    (
        "TBL-001",
        "pass-single-row",
        doc(
            [heading(0, "A"), block(1, "", "table")],
            tables=[table(1, rows=1, has_header_row=False)],
        ),
        [],
    ),
    (
        "TBL-002",
        "fail",
        doc([heading(0, "A"), block(1, "", "table")], tables=[table(1, has_merged_cells=True)]),
        [1],
    ),
    ("TBL-002", "pass", doc([heading(0, "A"), block(1, "", "table")], tables=[table(1)]), []),
    (
        "TBL-003",
        "fail",
        doc([heading(0, "A"), block(1, "", "table")], tables=[table(1, empty_cell_ratio=0.75)]),
        [1],
    ),
    (
        "TBL-003",
        "pass-at-half",
        doc([heading(0, "A"), block(1, "", "table")], tables=[table(1, empty_cell_ratio=0.5)]),
        [],
    ),
    ("LST-001", "fail-dashes", doc([heading(0, "A"), block(1, "- one"), block(2, "- two")]), [1]),
    (
        "LST-001",
        "fail-numbers",
        doc([heading(0, "A"), block(1, "1. one"), block(2, "2. two"), block(3, "3. three")]),
        [1],
    ),
    (
        "LST-001",
        "pass-single-line",
        doc([heading(0, "A"), block(1, "- one"), block(2, "Normal text.")]),
        [],
    ),
    (
        "LST-001",
        "pass-real-list",
        doc([heading(0, "A"), block(1, "one", "list_item"), block(2, "two", "list_item")]),
        [],
    ),
    ("CLR-001", "fail-grey", runs_doc("pale", Run(text="pale", color_hex="AAAAAA")), [1]),
    (
        "CLR-001",
        "fail-white-on-yellow",
        runs_doc("x", Run(text="x", color_hex="FFFFFF", highlight="YELLOW")),
        [1],
    ),
    ("CLR-001", "fail-hidden-white", runs_doc("x", Run(text="x", color_hex="FFFFFF")), [1]),
    ("CLR-001", "pass-default-black", runs_doc("x", Run(text="x")), []),
    (
        "CLR-001",
        "pass-large-text-lower-bar",
        runs_doc("x", Run(text="x", color_hex="888888", size_pt=18)),
        [],
    ),
    (
        "CLR-001",
        "fail-same-grey-small",
        runs_doc("x", Run(text="x", color_hex="888888", size_pt=11)),
        [1],
    ),
    ("TXT-001", "fail-dense", text_doc(DENSE), [1]),
    ("TXT-001", "pass-simple", text_doc(SIMPLE), []),
    (
        "TXT-001",
        "pass-too-short-to-score",
        text_doc("Notwithstanding comprehensive interdepartmental accountability."),
        [],
    ),
    (
        "TXT-002",
        "fail",
        text_doc("The red cat sat on the old mat by the door and " * 4 + "end."),
        [1],
    ),
    (
        "TXT-002",
        "pass",
        text_doc(
            "The red cat sat on the old mat by the door. The big dog lay on the rug by the fire."
        ),
        [],
    ),
    ("TXT-003", "fail", text_doc("PLEASE READ ALL THE INSTRUCTIONS NOW."), [1]),
    ("TXT-003", "pass-two-acronyms", text_doc("See the NASA FAQ page for details."), []),
    ("TXT-003", "pass-three-words", text_doc("Please READ THE TERMS before you start."), []),
    ("TXT-004", "fail", runs_doc("Pay by Friday", Run(text="Friday", underline=True)), [1]),
    (
        "TXT-004",
        "pass-link",
        runs_doc("Guide", Run(text="Guide", underline=True, hyperlink_url="https://example.org")),
        [],
    ),
    ("TXT-005", "fail", runs_doc("tiny", Run(text="tiny", size_pt=8)), [1]),
    ("TXT-005", "pass", runs_doc("normal", Run(text="normal", size_pt=11)), []),
    ("TXT-005", "pass-heading-is-not-body", doc([heading(0, "Small", 1)]), []),
]


@pytest.mark.parametrize(
    ("rule_id", "label", "document", "orders"), CASES, ids=lambda v: v if isinstance(v, str) else ""
)
def test_rule_fixture(
    rule_id: str, label: str, document: ParsedDocument, orders: list[int]
) -> None:
    findings, warnings = run_rules(document, only={rule_id})
    assert not warnings
    assert [f.location.block_order for f in findings] == orders
    assert all(f.rule_id == rule_id for f in findings)


def test_every_rule_has_a_passing_and_a_failing_fixture() -> None:
    from accesslens.rules import REGISTRY

    for rule_id in REGISTRY:
        outcomes = {bool(orders) for rid, _, _, orders in CASES if rid == rule_id}
        assert outcomes == {True, False}, rule_id


def test_a_clean_document_triggers_no_rule() -> None:
    from factories import good_doc

    findings, warnings = run_rules(good_doc())
    assert not findings
    assert not warnings
