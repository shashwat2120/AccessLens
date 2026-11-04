# AccessLens

**Audit Word documents for accessibility issues and get a prioritized fix list, mapped to WCAG 2.2.**

> Status: in development — see [`docs/06-ROADMAP.md`](docs/06-ROADMAP.md).

## What it does
Upload a .docx and AccessLens reports issues like missing or useless alt text, broken heading structure, unclear link text, tables without headers, low-contrast text, and hard-to-read passages, each with its location, why it matters, and how to fix it.

- **Rules first:** clear-cut checks are deterministic and fast.
- **AI for judgment calls:** an LLM reviews alt text against the actual image, suggests plain-language rewrites, and flags unclear links.
- **Use it anywhere:** web app, REST API, CLI, or as an MCP tool from Claude and other AI assistants.

## Privacy
Documents are never stored, and logs never contain document text. In AI mode, short text excerpts (with emails, phone numbers and long numbers masked; names are **not** detected) and images that have alt text are sent to the configured LLM provider. Images cannot be redacted. Free tiers may use prompts to improve the provider's products, so don't upload confidential documents to the public demo. **Rules-only mode** sends nothing to any AI service.

## Results
_Coming after Phase 8 — accuracy, latency, and limitations from [`docs/05-EVALUATION.md`](docs/05-EVALUATION.md)._

## Documentation
| Doc | Purpose |
|---|---|
| [PRD](docs/01-PRD.md) | What and why |
| [TRD](docs/02-TRD.md) | Architecture and technical design |
| [Security](docs/03-SECURITY.md) | Threat model and controls |
| [Rules catalog](docs/04-RULES-CATALOG.md) | Every check and its WCAG mapping |
| [Evaluation](docs/05-EVALUATION.md) | How accuracy is measured |
| [Roadmap](docs/06-ROADMAP.md) | Phases and checklist |
| [Engineering standards](docs/07-ENGINEERING-STANDARDS.md) | Code, tests, CI |
| [Decisions](docs/08-DECISIONS.md) | Why each choice was made |

## License
MIT
