from accesslens.config import Settings
from accesslens.llm.items import select_items, sniff_image_mime
from accesslens.models import Finding, Location, Severity, Source, WcagLevel
from factories import block, doc, heading, image, link

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
SETTINGS = Settings(_env_file=None)


def rule_finding(rule_id: str, order: int) -> Finding:
    return Finding(
        id=f"{rule_id}-b{order:04d}",
        rule_id=rule_id,
        title="t",
        severity=Severity.LOW,
        wcag_criterion=None,
        wcag_level=WcagLevel.A,
        location=Location(block_id=f"b{order:04d}", block_order=order, snippet=""),
        message="m",
        suggestion="s",
        source=Source.RULE,
    )


def test_mime_sniffing() -> None:
    assert sniff_image_mime(PNG) == "image/png"
    assert sniff_image_mime(b"\xff\xd8\xff\xe0abc") == "image/jpeg"
    assert sniff_image_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_image_mime(b"<svg></svg>") is None


def test_selects_each_kind_in_priority_order() -> None:
    document = doc(
        [
            heading(0, "Report"),
            block(1, "", "image"),
            block(2, "Read the guide for the SLA details."),
            block(3, "Hard dense paragraph."),
        ],
        images=[image(1, alt_text="Sales chart")],
        links=[link(2, "the guide", "https://example.org/guide?token=SECRET#frag")],
    )
    findings = [rule_finding("TXT-001", 3)]
    items, warnings = select_items(document, findings, {"i001": PNG}, SETTINGS)
    assert [i.rule_id for i in items] == ["IMG-003", "LNK-003", "TXT-006", "TXT-001"]
    assert not warnings
    assert items[0].image == PNG
    assert items[0].image_mime == "image/png"
    assert items[3].target_finding_id == "TXT-001-b0003"
    assert "SECRET" not in items[1].text
    assert "example.org/guide" in items[1].text
    assert len({i.id for i in items}) == len(items)


def test_pii_is_redacted_before_anything_is_sent() -> None:
    document = doc(
        [heading(0, "R"), block(1, "", "image")],
        images=[
            image(1, alt_text="Photo of jane@example.com", context_before="Call 020 7946 0958")
        ],
    )
    items, _ = select_items(document, [], {"i001": PNG}, SETTINGS)
    assert "jane@example.com" not in items[0].text
    assert "7946" not in items[0].text
    assert "[EMAIL]" in items[0].text


def test_images_already_flagged_by_rules_are_skipped() -> None:
    document = doc([heading(0, "R"), block(1, "", "image")], images=[image(1, alt_text="image")])
    items, _ = select_items(document, [rule_finding("IMG-002", 1)], {"i001": PNG}, SETTINGS)
    assert items == []


def test_decorative_and_alt_less_images_are_skipped() -> None:
    document = doc(
        [heading(0, "R"), block(1, "", "image"), block(2, "", "image")],
        images=[image(1, decorative=True), image(2, alt_text=None, id="i002", block_id="b0002")],
    )
    assert select_items(document, [], {}, SETTINGS)[0] == []


def test_unsupported_or_missing_image_falls_back_to_text_only_with_a_warning() -> None:
    document = doc(
        [heading(0, "R"), block(1, "", "image")], images=[image(1, alt_text="A chart of sales")]
    )
    items, warnings = select_items(document, [], {"i001": b"<svg/>"}, SETTINGS)
    assert items[0].image is None
    assert any("could not be sent for visual review" in w for w in warnings)


def test_oversized_image_is_not_sent() -> None:
    document = doc(
        [heading(0, "R"), block(1, "", "image")], images=[image(1, alt_text="A chart of sales")]
    )
    small_cap = Settings(_env_file=None, llm_max_image_mb=1)
    huge = PNG + b"0" * (1024 * 1024 + 1)
    items, warnings = select_items(document, [], {"i001": huge}, small_cap)
    assert items[0].image is None
    assert warnings


def test_links_flagged_by_rules_and_defined_acronyms_are_skipped() -> None:
    document = doc(
        [
            heading(0, "R"),
            block(1, "Click here to continue."),
            block(2, "The Service Level Agreement (SLA) sets targets for the SLA."),
        ],
        links=[link(1, "click here")],
    )
    items, _ = select_items(document, [rule_finding("LNK-001", 1)], {}, SETTINGS)
    assert items == []


def test_same_text_for_different_destinations_is_noted() -> None:
    document = doc(
        [heading(0, "R"), block(1, "Open the plan."), block(2, "Open the budget.")],
        links=[
            link(1, "Details", "https://example.org/plan"),
            link(2, "Details", "https://example.org/budget"),
        ],
    )
    items, _ = select_items(document, [], {}, SETTINGS)
    assert len(items) == 2
    assert all("2 different destinations" in i.text for i in items)


def test_identical_items_are_deduplicated_and_text_is_capped() -> None:
    long_text = "The SLA applies. " * 100
    document = doc([heading(0, "R"), block(1, long_text), block(2, long_text)])
    items, _ = select_items(document, [], {}, SETTINGS)
    assert len(items) == 1
    assert len(items[0].text) <= SETTINGS.llm_max_item_chars
