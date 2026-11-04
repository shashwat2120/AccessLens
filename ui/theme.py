"""Design tokens and global styles for the AccessLens UI.

Every text colour is chosen to reach WCAG AA contrast (4.5:1) on its background; a test checks
each pair in ``CONTRAST_PAIRS`` with the project's own contrast function. Colour is never the
only signal: severity is always spelled out in a chip, scores always carry a word.
"""

INK = "#14213D"
MUTED = "#4B5563"
BRAND = "#0A5C99"
BRAND_DARK = "#073B66"
CANVAS = "#F5F8FC"
SURFACE = "#FFFFFF"
BORDER = "#D5DEE9"

SEVERITIES = ("critical", "high", "medium", "low")
# label, text colour, background, border, accent (bars and rings; decorative only)
SEVERITY_STYLE = {
    "critical": ("Critical", "#8A1212", "#FDECEC", "#E8A8A8", "#C62828"),
    "high": ("High", "#8F3A0B", "#FFF1E6", "#F0BE96", "#E4590F"),
    "medium": ("Medium", "#734A00", "#FFF6D6", "#E8CC7A", "#C99400"),
    "low": ("Low", "#1B4F8F", "#EAF2FF", "#B3CBEA", "#3B82C4"),
}
# score band: minimum score, word, colour (text on white)
SCORE_BANDS = (
    (90, "Excellent", "#166534"),
    (70, "Good", BRAND),
    (40, "Needs work", "#7A4F00"),
    (0, "Poor", "#9B1C1C"),
)


def score_band(score: int) -> tuple[str, str]:
    for minimum, word, colour in SCORE_BANDS:
        if score >= minimum:
            return word, colour
    return SCORE_BANDS[-1][1], SCORE_BANDS[-1][2]


# (name, foreground, background): every one must reach 4.5:1
CONTRAST_PAIRS = [
    ("body text", INK, SURFACE),
    ("body text on canvas", INK, CANVAS),
    ("muted text", MUTED, SURFACE),
    ("muted text on canvas", MUTED, CANVAS),
    ("brand text", BRAND, SURFACE),
    ("button label", "#FFFFFF", BRAND),
    ("hero text", "#FFFFFF", BRAND_DARK),
    *[(f"{sev} chip", style[1], style[2]) for sev, style in SEVERITY_STYLE.items()],
    *[(f"score {word}", colour, SURFACE) for _, word, colour in SCORE_BANDS],
    ("fix panel text", INK, "#EEF8F2"),
    ("fix panel label", "#14532D", "#EEF8F2"),
    ("disabled button label", MUTED, "#DCE6F2"),
    ("badge text", MUTED, "#F8FAFC"),
    ("privacy callout", INK, "#EEF4FB"),
]

CSS = f"""
<style>
  :root {{ --ink:{INK}; --muted:{MUTED}; --brand:{BRAND}; --brand-dark:{BRAND_DARK};
           --canvas:{CANVAS}; --surface:{SURFACE}; --border:{BORDER}; }}
  html, body, [class*="css"], .stApp {{ font-family: Inter, "Segoe UI", system-ui, -apple-system,
    "Helvetica Neue", Arial, sans-serif; color: var(--ink); }}
  .block-container {{ max-width: 1560px; padding-left: 2.5rem; padding-right: 2.5rem; padding-top: 1.25rem; padding-bottom: 3rem; }}
  header[data-testid="stHeader"] {{ background: transparent; }}
  footer, #MainMenu {{ visibility: hidden; }}
  h1, h2, h3 {{ letter-spacing: -0.01em; color: var(--ink); }}
  a {{ color: var(--brand); }}

  /* hero */
  .al-hero {{ background: linear-gradient(135deg, {BRAND_DARK} 0%, {BRAND} 100%); color: #fff;
    border-radius: 18px; padding: 2.4rem 2.6rem; margin-bottom: 1.4rem;
    box-shadow: 0 10px 30px rgba(7,59,102,.22); display:grid;
    grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr); gap: 2.4rem; align-items:center; }}
  .al-preview {{ background:#fff; color:var(--ink); border-radius:16px; padding:1.1rem 1.25rem;
    box-shadow:0 14px 34px rgba(0,0,0,.28); }}
  .al-preview-label {{ font-size:.74rem; letter-spacing:.07em; text-transform:uppercase;
    font-weight:800; color:var(--muted); margin-bottom:.4rem; }}
  .al-preview-score {{ display:flex; align-items:center; gap:.9rem; margin-bottom:.5rem; }}
  .al-preview-score svg {{ width:92px; height:92px; }}
  .al-preview-word {{ font-size:1.25rem; font-weight:800; color:{BRAND}; }}
  .al-preview-row {{ display:flex; align-items:center; gap:.65rem; padding:.5rem 0;
    border-top:1px solid var(--border); font-size:.95rem; color:var(--ink); }}
  .al-card-title {{ font-size:1.5rem; font-weight:700; letter-spacing:-0.01em; color:var(--ink);
    margin:0 0 .85rem; }}
  .al-hero .al-brand {{ display:flex; align-items:center; gap:.7rem; font-weight:700;
    font-size:1.05rem; letter-spacing:.02em; opacity:.95; }}
  .al-hero h1 {{ color:#fff; font-size:2.35rem; line-height:1.15; margin:.9rem 0 .55rem; padding:0; }}
  .al-hero p {{ color:#fff; font-size:1.08rem; max-width: 46rem; margin:0 0 1.1rem; }}
  .al-pills {{ display:flex; flex-wrap:wrap; gap:.5rem; }}
  .al-pill {{ background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.35);
    border-radius:999px; padding:.28rem .8rem; font-size:.86rem; font-weight:600; color:#fff; }}

  /* workspace header and left rail */
  .al-topbar {{ background: linear-gradient(135deg, {BRAND_DARK} 0%, {BRAND} 100%); color:#fff;
    border-radius:14px; padding:.8rem 1.4rem; margin-bottom:1.3rem; display:flex;
    align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap; }}
  .al-topbar .al-brand {{ display:flex; align-items:center; gap:.7rem; font-weight:700;
    font-size:1.1rem; }}
  .al-topbar-tag {{ color:#fff; font-size:.92rem; }}
  .al-doc-name {{ font-weight:700; font-size:1.05rem; color:var(--ink); margin:.9rem 0 .5rem;
    word-break:break-word; }}

  /* generic card */
  .al-card {{ background: var(--surface); border:1px solid var(--border); border-radius:14px;
    padding:1.15rem 1.3rem; box-shadow:0 1px 2px rgba(20,33,61,.05); }}
  .al-card h3 {{ margin:0 0 .8rem; padding:0; font-size:1.5rem; font-weight:700; }}
  .al-checks {{ list-style:none; margin:0; padding:0; display:grid; gap:.5rem; }}
  .al-checks li {{ display:flex; gap:.6rem; align-items:flex-start; color:var(--ink); font-size:.95rem; }}
  .al-checks b {{ display:block; font-size:.95rem; }}
  .al-checks span.al-dot {{ flex:0 0 auto; width:.65rem; height:.65rem; margin-top:.45rem;
    border-radius:50%; background:var(--brand); }}
  .al-muted {{ color: var(--muted); font-size:.9rem; }}
  .al-privacy {{ background:#EEF4FB; border:1px solid #C9DAEE; border-radius:12px;
    padding:.85rem 1rem; color:var(--ink); font-size:.9rem; margin-top:.9rem; }}

  /* score + stats */
  .al-score {{ display:flex; flex-wrap:wrap; align-items:center; gap:.9rem 1.1rem; }}
  .al-score .al-word {{ font-size:1.3rem; font-weight:800; white-space:nowrap; }}
  .al-score .al-sub {{ color:var(--muted); font-size:.9rem; }}
  .al-stat {{ border-radius:14px; padding:.95rem 1.1rem; border:1px solid; height:100%; }}
  .al-stat .al-n {{ font-size:2rem; font-weight:800; line-height:1.05; }}
  .al-stat .al-l {{ font-size:.9rem; font-weight:700; letter-spacing:.02em; }}

  /* severity chips and findings */
  .al-chip {{ display:inline-block; border-radius:6px; padding:.12rem .55rem; font-size:.78rem;
    font-weight:800; letter-spacing:.04em; text-transform:uppercase; border:1px solid; }}
  .al-finding {{ background:var(--surface); border:1px solid var(--border); border-left-width:5px;
    border-radius:12px; padding:.85rem 1.05rem; margin:.55rem 0; }}
  .al-finding header {{ display:flex; flex-wrap:wrap; align-items:center; gap:.5rem; margin-bottom:.45rem; }}
  .al-rule {{ font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; font-weight:700;
    font-size:.88rem; color:var(--ink); }}
  .al-badge {{ border:1px solid var(--border); border-radius:6px; padding:.08rem .5rem;
    font-size:.78rem; color:var(--muted); background:#F8FAFC; text-decoration:none; }}
  .al-where {{ margin:.1rem 0 .5rem; color:var(--muted); font-size:.88rem; }}
  .al-where code {{ background:#F1F5F9; color:var(--ink); border-radius:5px; padding:.1rem .4rem;
    font-size:.84rem; word-break:break-word; }}
  .al-problem {{ margin:.2rem 0 .55rem; font-size:1rem; color:var(--ink); }}
  .al-fix {{ background:#EEF8F2; border:1px solid #BFE0CC; border-radius:9px; padding:.55rem .75rem;
    color:var(--ink); font-size:.94rem; }}
  .al-fix strong {{ display:block; font-size:.78rem; letter-spacing:.05em; text-transform:uppercase;
    color:#14532D; margin-bottom:.1rem; }}

  /* streamlit widgets */
  .stButton > button, [data-testid="stDownloadButton"] button {{ border-radius:10px; font-weight:650;
    padding:.5rem 1.1rem; }}
  .stButton > button[kind="primary"] {{ background:var(--brand); border-color:var(--brand); }}
  .stButton > button[kind="primary"]:hover {{ background:var(--brand-dark); border-color:var(--brand-dark); }}
  .stButton > button[kind="primary"]:disabled, .stButton > button:disabled {{
    background:#DCE6F2 !important; border-color:#C5D3E5 !important; color:#4B5563 !important;
    opacity:1 !important; }}
  .stButton > button:disabled p {{ color:#4B5563 !important; }}
  .al-checks, .al-checks li {{ margin-left:0 !important; padding-left:0 !important; }}
  [data-testid="stExpander"] details {{ background:var(--surface); border:1px solid var(--border);
    border-radius:12px; }}
  [data-testid="stExpander"] summary {{ font-weight:650; }}
  [data-testid="stFileUploaderDropzone"] {{ border-radius:12px; border:1.5px dashed #9DB6D3;
    background:#F8FBFF; }}
  .al-footer {{ margin-top:2.2rem; padding-top:1rem; border-top:1px solid var(--border);
    color:var(--muted); font-size:.86rem; }}
  @media (max-width: 900px) {{ .al-hero {{ grid-template-columns: 1fr; gap: 1.4rem; }} }}
  @media (max-width: 640px) {{ .al-hero {{ padding:1.4rem 1.2rem; }} .al-hero h1 {{ font-size:1.7rem; }} }}
</style>
"""
