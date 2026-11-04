"""AccessLens web UI. A client of the API: it holds the API key server-side only.

Configure with environment variables ``ACCESSLENS_API_URL`` and ``ACCESSLENS_API_KEY`` (or
Streamlit secrets of the same names). Run: ``streamlit run ui/streamlit_app.py``.
Document-derived text only ever reaches the page through ``components`` (escaped).
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import streamlit as st

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from client import AccessLensClient, ApiError  # noqa: E402
from components import (  # noqa: E402
    checks_card_html,
    e,
    finding_html,
    footer_html,
    group_findings,
    hero_html,
    privacy_html,
    score_card_html,
    stat_card_html,
    topbar_html,
)
from theme import CSS, SEVERITIES, SEVERITY_STYLE  # noqa: E402

SAMPLE = HERE / "samples" / "sample-quarterly-report.docx"
SHOWN_PER_GROUP = 15
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _setting(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, os.environ.get(name, default)))
    except Exception:  # no secrets file configured
        return os.environ.get(name, default)


def _client() -> AccessLensClient:
    return AccessLensClient(
        _setting("ACCESSLENS_API_URL", "http://localhost:8000"), _setting("ACCESSLENS_API_KEY")
    )


def run_check(data: bytes, name: str, ai_review: bool) -> None:
    client = _client()
    try:
        with st.spinner("Checking your document..."):
            report = client.audit(data, rules_only=not ai_review)
            try:
                rules = {r["id"]: r for r in client.rules()}
            except Exception:  # the findings are still useful without the WCAG links
                rules = {}
    except ApiError as exc:
        st.session_state.pop("result", None)
        st.error(f"Could not check this file: {exc}")
        return
    except Exception:
        st.session_state.pop("result", None)
        st.error("The service is not reachable right now. Please try again later.")
        return
    st.session_state["result"] = {
        "name": name,
        "data": data,
        "ai_review": ai_review,
        "report": report,
        "rules": rules,
    }


def render_summary(result: dict[str, Any]) -> list[dict[str, Any]]:
    """The left rail: score, counts, filters and downloads. Returns the findings to show."""
    report = result["report"]
    findings = report["findings"]
    st.markdown(f'<div class="al-doc-name">{e(result["name"])}</div>', unsafe_allow_html=True)
    st.markdown(
        score_card_html(report["score"], len(findings), report["mode"]), unsafe_allow_html=True
    )
    pairs = list(zip(SEVERITIES, st.columns(2, gap="small") * 2, strict=True))
    for severity, column in pairs:
        column.markdown(
            stat_card_html(severity, report["counts"][severity]), unsafe_allow_html=True
        )
    for warning in report["warnings"]:
        st.info(warning)
    if not findings:
        return []

    chosen = st.pills(
        "Show severities",
        options=list(SEVERITIES),
        default=list(SEVERITIES),
        selection_mode="multi",
        format_func=lambda s: SEVERITY_STYLE[s][0],
    )
    query = (
        st.text_input("Search findings", placeholder="Search by rule, text or fix...")
        .strip()
        .lower()
    )
    render_downloads(result)
    return [
        f
        for f in findings
        if f["severity"] in (chosen or [])
        and (
            not query
            or query
            in " ".join((f["rule_id"], f["title"], f["message"], f["location"]["snippet"])).lower()
        )
    ]


def render_downloads(result: dict[str, Any]) -> None:
    client, data, ai = _client(), result["data"], result["ai_review"]
    st.markdown("**Download the report**")
    st.download_button(
        "HTML report",
        data=lambda: client.audit(data, rules_only=not ai, fmt="html"),
        file_name="accessibility-report.html",
        mime="text/html",
        width="stretch",
    )
    st.download_button(
        "Spreadsheet (XLSX)",
        data=lambda: client.audit(data, rules_only=not ai, fmt="xlsx"),
        file_name="accessibility-report.xlsx",
        mime=XLSX,
        width="stretch",
    )
    st.download_button(
        "Raw data (JSON)",
        data=json.dumps(result["report"], indent=2),
        file_name="accessibility-report.json",
        mime="application/json",
        width="stretch",
    )


def render_findings(result: dict[str, Any], visible: list[dict[str, Any]]) -> None:
    rules = result["rules"]
    st.markdown("## Findings, most important first")
    if not result["report"]["findings"]:
        st.success("No issues were found by the checks that ran. Well done.")
        return
    if not visible:
        st.info("No findings match these filters.")
    for group in group_findings(visible):
        items = group["items"]
        label = (
            f"{SEVERITY_STYLE[group['severity']][0]}  ·  {group['rule_id']}  ·  "
            f"{group['title']}  ·  "
            f"{len(items)} finding{'s' if len(items) != 1 else ''}"
        )
        with st.expander(
            label, expanded=group["severity"] in ("critical", "high") and len(items) <= 5
        ):
            for finding in items[:SHOWN_PER_GROUP]:
                st.markdown(
                    finding_html(finding, rules.get(finding["rule_id"])), unsafe_allow_html=True
                )
            if len(items) > SHOWN_PER_GROUP:
                st.caption(
                    f"Showing {SHOWN_PER_GROUP} of {len(items)}. "
                    "The spreadsheet download lists them all."
                )


def render_form(title: str) -> tuple[bool, bool, Any, bool]:
    with st.container(border=True):
        st.markdown(f'<div class="al-card-title">{e(title)}</div>', unsafe_allow_html=True)
        ai_review = st.toggle(
            "Add AI review of alt text, links and jargon",
            value=False,
            key="ai_review",
            help="Off by default. When on, short text excerpts and images with alt text "
            "are sent to Google Gemini (Groq as a fallback).",
        )
        upload = st.file_uploader("Word document (.docx, up to 10 MB)", type=["docx"], key="upload")
        check, sample = st.columns(2)
        run = check.button(
            "Check accessibility", type="primary", disabled=upload is None, width="stretch"
        )
        try_sample = sample.button("Try a sample document", width="stretch")
    return run, try_sample, upload, ai_review


def main() -> None:
    st.set_page_config(
        page_title="AccessLens: Word accessibility checker", page_icon="🔍", layout="wide"
    )
    st.markdown(CSS, unsafe_allow_html=True)
    result = st.session_state.get("result")

    if result is None:
        st.markdown(hero_html(), unsafe_allow_html=True)
        form, about = st.columns([1.35, 1], gap="large")
        with form:
            run, try_sample, upload, ai_review = render_form("Check a document")
            st.markdown(privacy_html(), unsafe_allow_html=True)
        with about:
            st.markdown(checks_card_html(), unsafe_allow_html=True)
    else:
        # a workspace: summary and the next check on the left, the findings on the right
        st.markdown(topbar_html(), unsafe_allow_html=True)
        rail, main_col = st.columns([1, 2.3], gap="large")
        with rail:
            run, try_sample, upload, ai_review = render_form("Check another document")
            visible = render_summary(result)
        with main_col:
            render_findings(result, visible)

    if run and upload is not None:
        run_check(upload.getvalue(), upload.name, ai_review)
        st.rerun()
    elif try_sample:
        run_check(SAMPLE.read_bytes(), "the sample document", ai_review)
        st.rerun()
    st.markdown(footer_html(), unsafe_allow_html=True)


main()
