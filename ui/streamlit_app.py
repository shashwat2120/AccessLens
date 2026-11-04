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
    finding_html,
    footer_html,
    group_findings,
    hero_html,
    privacy_html,
    score_card_html,
    stat_card_html,
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


def render_results(result: dict[str, Any]) -> None:
    report, rules = result["report"], result["rules"]
    findings = report["findings"]
    counts = report["counts"]

    st.markdown(f"## Results for {result['name']}")
    left, right = st.columns([1.6, 2.4], gap="medium")
    with left:
        st.markdown(
            score_card_html(report["score"], len(findings), report["mode"]), unsafe_allow_html=True
        )
    with right:
        for column, severity in zip(st.columns(4, gap="small"), SEVERITIES, strict=True):
            column.markdown(stat_card_html(severity, counts[severity]), unsafe_allow_html=True)

    for warning in report["warnings"]:
        st.info(warning)
    if not findings:
        st.success("No issues were found by the checks that ran. Well done.")
        return

    st.markdown("### Findings, most important first")
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
    visible = [
        f
        for f in findings
        if f["severity"] in (chosen or [])
        and (
            not query
            or query
            in " ".join((f["rule_id"], f["title"], f["message"], f["location"]["snippet"])).lower()
        )
    ]
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

    st.markdown("### Download the report")
    client, data, ai = _client(), result["data"], result["ai_review"]
    html_col, xlsx_col, json_col = st.columns(3)
    html_col.download_button(
        "HTML report",
        data=lambda: client.audit(data, rules_only=not ai, fmt="html"),
        file_name="accessibility-report.html",
        mime="text/html",
        width="stretch",
    )
    xlsx_col.download_button(
        "Spreadsheet (XLSX)",
        data=lambda: client.audit(data, rules_only=not ai, fmt="xlsx"),
        file_name="accessibility-report.xlsx",
        mime=XLSX,
        width="stretch",
    )
    json_col.download_button(
        "Raw data (JSON)",
        data=json.dumps(report, indent=2),
        file_name="accessibility-report.json",
        mime="application/json",
        width="stretch",
    )


def main() -> None:
    st.set_page_config(
        page_title="AccessLens: Word accessibility checker", page_icon="🔍", layout="wide"
    )
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(hero_html(), unsafe_allow_html=True)

    form, about = st.columns([1.35, 1], gap="large")
    with form:
        with st.container(border=True):
            st.markdown('<div class="al-card-title">Check a document</div>', unsafe_allow_html=True)
            ai_review = st.toggle(
                "Add AI review of alt text, links and jargon",
                value=False,
                help="Off by default. When on, short text excerpts and images with alt text "
                "are sent to Google Gemini (Groq as a fallback).",
            )
            upload = st.file_uploader("Word document (.docx, up to 10 MB)", type=["docx"])
            check, sample = st.columns(2)
            run = check.button(
                "Check accessibility", type="primary", disabled=upload is None, width="stretch"
            )
            try_sample = sample.button("Try a sample document", width="stretch")
        st.markdown(privacy_html(), unsafe_allow_html=True)
    with about:
        st.markdown(checks_card_html(), unsafe_allow_html=True)

    if run and upload is not None:
        run_check(upload.getvalue(), upload.name, ai_review)
    elif try_sample:
        run_check(SAMPLE.read_bytes(), "the sample document", ai_review)

    if "result" in st.session_state:
        st.divider()
        render_results(st.session_state["result"])
    st.markdown(footer_html(), unsafe_allow_html=True)


main()
