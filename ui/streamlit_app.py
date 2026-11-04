"""Streamlit front end. A thin client of the API: it holds the API key server-side only.

Configure with environment variables ``ACCESSLENS_API_URL`` and ``ACCESSLENS_API_KEY`` (or
Streamlit secrets of the same names). Run: ``streamlit run ui/streamlit_app.py``.
"""

import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from client import AccessLensClient, ApiError

PRIVACY = (
    "Your document is processed in memory and is not stored. In **AI review** mode, short "
    "excerpts of text, and images that have alt text, are sent to a third-party AI provider "
    "(Google Gemini, with Groq as a fallback). Free AI tiers may use what they receive to "
    "improve their products, so do not upload confidential documents in AI review mode on "
    "this public demo. **Rules only** mode sends nothing to any AI service."
)
SEVERITY_ORDER = ("critical", "high", "medium", "low")


def _setting(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, os.environ.get(name, default)))
    except Exception:  # no secrets file configured
        return os.environ.get(name, default)


def _client() -> AccessLensClient:
    return AccessLensClient(
        _setting("ACCESSLENS_API_URL", "http://localhost:8000"), _setting("ACCESSLENS_API_KEY")
    )


def render_report(report: dict) -> None:
    st.header("Results")
    left, right = st.columns([1, 3])
    left.metric("Score", f"{report['score']} / 100")
    counts = report["counts"]
    right.write(
        "Findings: "
        + ", ".join(f"{counts[s]} {s}" for s in SEVERITY_ORDER)
        + f" · Mode: {'rules only' if report['mode'] == 'rules_only' else 'rules and AI review'}"
    )
    for warning in report["warnings"]:
        st.info(warning)
    findings = report["findings"]
    if not findings:
        st.success("No issues were found by the checks that ran.")
        return
    st.subheader(f"{len(findings)} issue{'s' if len(findings) != 1 else ''}, most important first")
    st.dataframe(
        [
            {
                "Severity": f["severity"].capitalize(),
                "Rule": f["rule_id"],
                "Where": f"Block {f['location']['block_order']}: {f['location']['snippet']}",
                "Problem": f["message"],
                "How to fix": f["suggestion"],
                "Source": "AI" if f["source"] == "llm" else "Rule",
            }
            for f in findings
        ],
        column_config={
            "Severity": st.column_config.TextColumn("Severity", width="small"),
            "Rule": st.column_config.TextColumn("Rule", width="small"),
            "Where": st.column_config.TextColumn("Where", width="large"),
            "Problem": st.column_config.TextColumn("Problem", width="large"),
            "How to fix": st.column_config.TextColumn("How to fix", width="large"),
            "Source": st.column_config.TextColumn("Source", width="small"),
        },
        hide_index=True,
        width="stretch",
    )


def main() -> None:
    st.set_page_config(page_title="AccessLens", layout="wide")
    st.title("AccessLens")
    st.write("Check a Word document for accessibility problems and get a prioritized fix list.")
    st.info(PRIVACY)

    rules_only = st.toggle(
        "Rules only (send nothing to any AI service)",
        value=True,
        help="Turn off to add AI review of alt text, link text and jargon.",
    )
    upload = st.file_uploader("Word document (.docx, up to 10 MB)", type=["docx"])
    if upload is None:
        return
    if st.button("Check accessibility", type="primary"):
        client = _client()
        data = upload.getvalue()
        try:
            with st.spinner("Checking..."):
                st.session_state["report"] = client.audit(data, rules_only=rules_only)
                st.session_state["html"] = client.audit(data, rules_only=rules_only, fmt="html")
                st.session_state["xlsx"] = client.audit(data, rules_only=rules_only, fmt="xlsx")
        except ApiError as exc:
            st.session_state.pop("report", None)
            st.error(f"Could not check this file: {exc}")
        except Exception:
            st.session_state.pop("report", None)
            st.error("The service is not reachable right now. Please try again later.")

    report = st.session_state.get("report")
    if report:
        render_report(report)
        st.subheader("Download")
        st.download_button(
            "Download report (HTML)",
            st.session_state["html"],
            "accessibility-report.html",
            "text/html",
        )
        st.download_button(
            "Download spreadsheet (XLSX)",
            st.session_state["xlsx"],
            "accessibility-report.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


main()
