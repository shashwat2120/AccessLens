# 02 — Technical Requirements & Design (TRD)

**Status:** Draft v1.0 · **Last updated:** 2026-11-03
Read with: `01-PRD.md` (what), `03-SECURITY.md` (constraints), `04-RULES-CATALOG.md` (checks).

---

## 1. Architecture overview

```
            ┌──────────────┐  ┌──────────┐  ┌────────────┐  ┌──────────────┐
 Clients →  │ Streamlit UI │  │   CLI    │  │ MCP server │  │ REST clients │
            └──────┬───────┘  └────┬─────┘  └─────┬──────┘  └──────┬───────┘
                   │ HTTPS         │ in-process   │ in-process     │ HTTPS
                   ▼               ▼              ▼                ▼
            ┌─────────────────────────────────────────────────────────────┐
            │  FastAPI (auth, rate limit, size limits)  →  Audit Service   │
            └──────────────────────────────┬──────────────────────────────┘
                                           ▼
   ┌──────────────────────── LangGraph audit pipeline ─────────────────────────┐
   │ validate → parse → rule_checks → select_llm_items → llm_checks → merge    │
   │                                      (skipped in rules-only mode) → report│
   └───────────────────────────────────────────────────────────────────────────┘
                         │                                   │
               python-docx / lxml (sandboxed)      LLM provider layer
                                                   Gemini (primary) / Groq (fallback)
```

All interfaces call one `AuditService.audit(file_bytes, options) -> Report`. No business logic lives in the API, CLI, UI or MCP layers.

## 2. Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| Dependency mgmt | uv (`pyproject.toml` + `uv.lock`) |
| Parsing | python-docx, lxml (+ zipfile pre-validation) |
| Readability | textstat |
| Agent orchestration | LangGraph |
| LLM access | LangChain chat model integrations (`langchain-google-genai`, `langchain-groq`) |
| Structured output | Pydantic v2 |
| API | FastAPI + Uvicorn |
| Rate limiting | slowapi |
| Reports | Jinja2 (HTML, autoescape on), openpyxl/pandas (XLSX) |
| MCP | Official MCP Python SDK (`mcp`), stdio transport |
| UI | Streamlit (calls the API, never the pipeline directly) |
| Config | pydantic-settings |
| Logging | structlog (JSON) |
| Tracing | LangSmith (dev only, inputs/outputs hidden in prod — see security) |
| Tests | pytest, pytest-cov, hypothesis (fuzzing parser) |
| Quality | ruff, mypy (strict), bandit, pip-audit, gitleaks |
| Container | Docker (python slim, non-root) |
| Hosting | Hugging Face Spaces (Docker) or Render free tier |

## 3. Data model (Pydantic, `src/accesslens/models.py`)

```python
class Severity(StrEnum): CRITICAL, HIGH, MEDIUM, LOW
class WcagLevel(StrEnum): A, AA, AAA, BEST_PRACTICE
class Source(StrEnum): RULE, LLM

class DocMeta(BaseModel):
    title: str | None
    language: str | None
    word_count: int
    paragraph_count: int
    image_count: int
    table_count: int
    sha256: str                # of the uploaded file; never the filename
    # Author/last-modified-by deliberately NOT stored (PII)

class Run(BaseModel):         # a formatted span inside a paragraph
    text: str; bold: bool; italic: bool; underline: bool
    size_pt: float | None; color_hex: str | None; highlight: str | None
    hyperlink_url: str | None  # set if run is inside a hyperlink

class Block(BaseModel):
    id: str                    # "b0042" — stable order-based id
    order: int
    type: Literal["heading","paragraph","list_item","table","image","title"]
    text: str
    style_name: str | None
    heading_level: int | None  # 1–9 for real heading styles
    runs: list[Run] = []

class ImageInfo(BaseModel):
    id: str; block_id: str
    alt_text: str | None       # wp:docPr/@descr
    title: str | None          # wp:docPr/@title
    decorative: bool           # adec:decorative extension
    inline: bool               # wp:inline vs wp:anchor (floating)
    width_px: int | None; height_px: int | None
    image_sha256: str
    context_before: str; context_after: str   # ≤ 300 chars each

class TableInfo(BaseModel):
    id: str; block_id: str; rows: int; cols: int
    has_header_row: bool       # first row has w:tblHeader
    empty_cell_ratio: float; has_merged_cells: bool

class LinkInfo(BaseModel):
    block_id: str; text: str; url: str | None; external: bool

class ParsedDocument(BaseModel):
    meta: DocMeta; blocks: list[Block]; images: list[ImageInfo]
    tables: list[TableInfo]; links: list[LinkInfo]

class Location(BaseModel):
    block_id: str; block_order: int; snippet: str   # ≤ 120 chars

class Finding(BaseModel):
    id: str; rule_id: str; title: str
    severity: Severity; wcag_criterion: str | None; wcag_level: WcagLevel
    location: Location; message: str; suggestion: str
    source: Source; confidence: float = 1.0          # rules = 1.0

class Report(BaseModel):
    report_version: str = "1.0"
    generated_at: datetime; meta: DocMeta
    score: int                                       # 0–100
    counts: dict[Severity, int]
    findings: list[Finding]                          # sorted by priority
    llm: LlmUsage | None                             # provider, model, calls, tokens, degraded flag
    mode: Literal["full","rules_only"]
    warnings: list[str]                              # e.g. "LLM budget reached; 4 items not reviewed"
```

Images bytes are held in memory only for the duration of the request (for vision checks) and never written to the report.

## 4. Pipeline (LangGraph)

State: `AuditState { file_bytes, options, parsed, rule_findings, llm_items, llm_findings, report, errors }`

| Node | Does | Failure behavior |
|---|---|---|
| `validate` | Zip/size/content-type/macro/DOCTYPE checks (`03-SECURITY.md` §3) | Reject with typed error → 4xx |
| `parse` | Build `ParsedDocument` in a subprocess with time + memory limits | Timeout/crash → 422 "could not parse" |
| `rule_checks` | Run every enabled rule from registry; pure functions `(ParsedDocument) -> list[Finding]` | One rule crashing is logged and reported in `warnings`; others continue |
| `select_llm_items` | Pick candidates for LLM review (images with alt text, hard paragraphs, ambiguous links); dedupe by hash; cap at budget | — |
| `llm_checks` | Batch items into ≤ budget calls, call provider with structured output, validate | Retry w/ backoff on 429/5xx → fallback provider → mark `degraded`, keep rule findings |
| `merge` | Combine, dedupe (same rule+block), prioritize, score | — |
| `report` | Build `Report` | — |

Conditional edge: if `options.mode == "rules_only"` → skip `select_llm_items` and `llm_checks`.

Each node is a plain function in `agent/nodes.py`; the graph is wired in `agent/graph.py`. No node gets tools or the ability to call other services beyond what is listed — the LLM has **zero tools** (see Security: excessive agency).

## 5. LLM layer

- `llm/provider.py` exposes `get_chat_model(role: "vision"|"text") -> BaseChatModel` driven by config:
  `LLM_PRIMARY=gemini`, `LLM_FALLBACK=groq`, model names in config (never hard-coded).
- **Default models:** a current Gemini Flash / Flash-Lite model (vision-capable) as primary; a Groq-hosted open model as text fallback. Check exact model names and free limits in Google AI Studio and the Groq console when you start; record them in `08-DECISIONS.md`.
- If the fallback model lacks vision, the alt-text check runs text-only (alt text + surrounding paragraph) and the finding's confidence is lowered by 0.2.
- **Batching:** up to 8 items per call, each with an item id; response is a list keyed by id. Saves requests-per-day on the free tier.
- **Structured output:** `with_structured_output(LlmBatchResult)`; anything failing validation is retried once, then dropped and noted in `warnings`.
- **Allowed outputs:** the LLM may only emit findings for rule IDs `IMG-003`, `TXT-006`, `LNK-003` and rewrite suggestions for `TXT-001`/`TXT-002`. It cannot delete or change rule-based findings.
- **Cache:** key = sha256(prompt template version + item content + model). In-memory LRU in prod; optional on-disk cache in dev to save quota.
- **Limits:** per-call timeout 30 s; per-document budget default 10 calls; global concurrency 2 (free-tier friendly); client-side token bucket per provider limits.
- Prompts live in `llm/prompts/*.md`, versioned (`v1`, `v2`), and the version is recorded in `Report.llm`.

## 6. Prioritization & score

Priority sort key: `(severity_rank, wcag_level_rank, -occurrences_of_rule, block_order)`.
Severity weights: critical 10, high 5, medium 2, low 1.
`score = max(0, round(100 - Σ weight × min(count_per_rule, 5) × 100 / normalizer))`, normalizer = 60 (tuned in eval). Capping per-rule count stops one repeated issue from zeroing the score. Score formula is documented in the report footer.

## 7. Interfaces

### REST API (`/v1`)
| Method | Path | Description |
|---|---|---|
| POST | `/v1/audits` | multipart `file` (one .docx) + `mode`, `target_grade`; returns `Report` JSON. `Accept: text/html` or `?format=html\|xlsx` returns that format |
| POST | `/v1/audits/batch` | up to 20 files; returns `{reports: [...], summary}` |
| GET | `/v1/rules` | rule catalog (ids, titles, severity, WCAG) |
| GET | `/healthz` | liveness |
| GET | `/readyz` | readiness (config loaded; does not call LLM) |

Auth: `X-API-Key` header. Errors: RFC 9457 `application/problem+json` with stable `type` codes (`invalid_file`, `file_too_large`, `macro_enabled`, `parse_failed`, `rate_limited`, `unauthorized`). OpenAPI docs disabled in prod.

### CLI
`accesslens audit <path|dir> [--rules-only] [--format json|html|xlsx] [--out DIR] [--target-grade 9]`
Exit codes: 0 no critical/high, 1 critical/high found (CI-friendly), 2 error.

### MCP server (stdio)
| Tool | Input | Output |
|---|---|---|
| `audit_docx` | `path` (inside allowed dir), `rules_only` | Report summary + top 25 findings |
| `list_rules` | — | rule catalog |
| `explain_rule` | `rule_id` | description, WCAG link, how to fix |

Path handling per `03-SECURITY.md` §8.

## 8. Configuration (env vars, `.env.example`)

```
APP_ENV=dev|prod
API_KEYS_SHA256=comma,separated,hashes
GEMINI_API_KEY=            # SecretStr
GROQ_API_KEY=              # SecretStr
LLM_PRIMARY=gemini
LLM_FALLBACK=groq
LLM_MODEL_PRIMARY=
LLM_MODEL_FALLBACK=
LLM_BUDGET_PER_DOC=10
LLM_ENABLED=true
PII_REDACTION=true
MAX_UPLOAD_MB=10
MAX_BATCH_FILES=20
TARGET_GRADE=9
RATE_LIMIT=20/minute
CORS_ORIGINS=https://<your-ui-domain>
MCP_ALLOWED_DIR=/data/inbox
LANGSMITH_TRACING=false
```

## 9. Repository layout

```
accesslens/
├── CLAUDE.md  README.md  SECURITY.md  LICENSE
├── pyproject.toml  uv.lock  .env.example  .gitignore
├── .pre-commit-config.yaml  Dockerfile  docker-compose.yml
├── .github/workflows/ci.yml  .github/dependabot.yml
├── docs/                      # these documents
├── src/accesslens/
│   ├── config.py  models.py  errors.py  logging.py  service.py  cli.py
│   ├── ingest/      validate.py  parse_docx.py  sandbox.py
│   ├── rules/       base.py (registry)  images.py  headings.py  links.py
│   │                tables.py  text.py  color.py  document.py  lists.py
│   ├── llm/         provider.py  checks.py  cache.py  redact.py  prompts/
│   ├── agent/       state.py  nodes.py  graph.py
│   ├── report/      prioritize.py  score.py  html.py  xlsx.py  templates/
│   ├── api/         main.py  routes.py  auth.py  limits.py  problems.py
│   └── mcp_server/  server.py
├── ui/streamlit_app.py
├── eval/            generate_corpus.py  answer_key.csv  run_eval.py  corpus/  results/
└── tests/           unit/  integration/  security/  fixtures/
```

## 10. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | See PRD §7. Parsing a 100-page doc < 5 s. |
| Reliability | LLM outage never fails an audit; it degrades to rules-only with a warning. |
| Observability | JSON logs with request id, file sha256, size, durations per node, finding counts, LLM calls/tokens. Never document text. |
| Scalability | Stateless; horizontal scaling behind the platform's load balancer. |
| Accessibility of our own UI | Streamlit app and HTML report pass our own checks' spirit: proper headings, contrast ≥ 4.5:1, keyboard usable, alt text on any images. |
| Determinism | Rule checks fully deterministic; LLM temperature 0. |
