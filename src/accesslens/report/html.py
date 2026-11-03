"""HTML report (SECURITY §9): autoescaped, no scripts, no ``|safe`` on document text."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from accesslens.models import Report
from accesslens.report.score import FORMULA

# Served with: Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'
HTML_CSP = "default-src 'none'; style-src 'unsafe-inline'"

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"], default=True),
    undefined=StrictUndefined,
)


def render_html(report: Report, *, normalizer: int = 60) -> str:
    """Render ``report`` to a self-contained HTML page."""
    return _ENV.get_template("report.html").render(
        report=report,
        counts=[(severity.value, count) for severity, count in report.counts.items()],
        formula=FORMULA.format(normalizer=normalizer),
    )
