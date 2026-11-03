# 04 — Rules Catalog

**Status:** Draft v1.0 · **Last updated:** 2026-11-03
Source of truth for every check. Each rule has a unit test with at least one passing and one failing fixture. WCAG references are to **WCAG 2.2**.

Severity guide: **Critical** = content unusable for some users · **High** = major barrier · **Medium** = noticeable barrier · **Low** = best practice / polish.

## Images (IMG)
| ID | Check | How | Severity | WCAG |
|---|---|---|---|---|
| IMG-001 | Image has no alt text and is not marked decorative | Rule: `descr` empty and `decorative=false` | Critical | 1.1.1 Non-text Content (A) |
| IMG-002 | Alt text is a placeholder: filename (`.png`, `.jpg`…), "image", "picture", "graphic", "photo", "screenshot" alone, or < 4 chars | Rule | High | 1.1.1 (A) |
| IMG-003 | Alt text exists but does not describe the image's content/purpose | **LLM + vision** (alt text + image + context) | Medium | 1.1.1 (A) |
| IMG-004 | Alt text too long (> 250 chars) — should be a caption or long description | Rule | Low | 1.1.1 (A) |
| IMG-005 | Floating (anchored) image may break reading order | Rule: `wp:anchor` | Medium | 1.3.2 Meaningful Sequence (A) |

## Headings (HDG)
| ID | Check | How | Severity | WCAG |
|---|---|---|---|---|
| HDG-001 | Document > 300 words with no heading styles | Rule | High | 1.3.1 Info and Relationships (A), 2.4.6 Headings and Labels (AA) |
| HDG-002 | Skipped heading level (e.g., H1 → H3) | Rule | Medium | 1.3.1 (A) |
| HDG-003 | "Fake heading": short paragraph (≤ 12 words), fully bold or ≥ 14 pt, followed by body text, but not a heading style | Rule (heuristic, confidence 0.8) | Medium | 1.3.1 (A) |
| HDG-004 | Empty heading | Rule | Low | 2.4.6 (AA) |
| HDG-005 | Document does not start with H1/Title, or has more than one H1 | Rule | Low | Best practice |

## Document properties (DOC)
| ID | Check | How | Severity | WCAG |
|---|---|---|---|---|
| DOC-001 | Document title property is empty | Rule: core props `title` | Medium | 2.4.2 Page Titled (A) |
| DOC-002 | Default document language not set | Rule: `w:lang` in styles defaults | Medium | 3.1.1 Language of Page (A) |

## Links (LNK)
| ID | Check | How | Severity | WCAG |
|---|---|---|---|---|
| LNK-001 | Non-descriptive link text: "click here", "here", "read more", "link", "more", "this" | Rule (case-insensitive list) | Medium | 2.4.4 Link Purpose (In Context) (A) |
| LNK-002 | Raw URL used as link text | Rule: text looks like URL | Low | 2.4.4 (A) |
| LNK-003 | Link text unclear even in context (e.g., same text points to different URLs, vague phrases not in list) | **LLM** (text) | Low | 2.4.4 (A) |

## Tables (TBL)
| ID | Check | How | Severity | WCAG |
|---|---|---|---|---|
| TBL-001 | Data table (≥ 2 rows and ≥ 2 cols) without a header row marked "repeat as header" | Rule: no `w:tblHeader` on row 1 | High | 1.3.1 (A) |
| TBL-002 | Merged or split cells (complex table) | Rule: `gridSpan`/`vMerge` | Medium | 1.3.1 (A) |
| TBL-003 | Mostly empty table (> 50% empty cells) — likely used for layout | Rule | Low | 1.3.1 (A) |

## Lists (LST)
| ID | Check | How | Severity | WCAG |
|---|---|---|---|---|
| LST-001 | "Fake list": consecutive paragraphs starting with `-`, `*`, `•`, `1.`, `a)` typed manually instead of list formatting | Rule | Low | 1.3.1 (A) |

## Colour & contrast (CLR)
| ID | Check | How | Severity | WCAG |
|---|---|---|---|---|
| CLR-001 | Text colour contrast < 4.5:1 (< 3:1 for ≥ 18 pt or ≥ 14 pt bold) against white or its highlight/shading colour | Rule: WCAG relative luminance formula on run colour | High | 1.4.3 Contrast (Minimum) (AA) |

## Text & readability (TXT)
| ID | Check | How | Severity | WCAG |
|---|---|---|---|---|
| TXT-001 | Section reading grade (Flesch-Kincaid) above `TARGET_GRADE` (default 9) | Rule detects; **LLM** suggests a plain-language rewrite | Medium | 3.1.5 Reading Level (AAA) |
| TXT-002 | Sentence longer than 30 words | Rule detects; **LLM** suggests split | Low | 3.1.5 (AAA) |
| TXT-003 | Long run of ALL CAPS text (> 3 consecutive words) | Rule | Low | Best practice |
| TXT-004 | Underlined text that is not a link | Rule | Low | Best practice |
| TXT-005 | Body text smaller than 10 pt | Rule | Low | Best practice |
| TXT-006 | Unexplained jargon or acronym on first use | **LLM** | Low | 3.1.3 Unusual Words (AAA), 3.1.4 Abbreviations (AAA) |

## Adding a new rule
1. Add a row here with a new ID (never reuse IDs).
2. Implement in the matching `rules/*.py` file and register it in the registry.
3. Add pass + fail fixtures and unit tests.
4. Add at least one planted instance to the eval corpus and answer key.
5. Note the change in `CHANGELOG.md`.

## Known limitations (documented in README)
- Contrast assumes a white page unless shading/highlight is set; theme colours are resolved where possible.
- Text inside images (scanned text, charts) is not read except through IMG-003's vision check.
- Colour used alone to convey meaning (WCAG 1.4.1) is not checked in v1.
