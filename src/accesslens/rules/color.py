"""Colour contrast rule CLR-001 (WCAG relative luminance, assuming a white page)."""

from accesslens.models import ParsedDocument, Run, Severity, WcagLevel
from accesslens.rules.base import Hit, RuleConfig, rule

_PAGE = "FFFFFF"
_TEXT_DEFAULT = "000000"
# Word highlight names (WD_COLOR_INDEX) to their colours.
_HIGHLIGHTS = {
    "BLACK": "000000",
    "BLUE": "0000FF",
    "BRIGHT_GREEN": "00FF00",
    "DARK_BLUE": "000080",
    "DARK_RED": "800000",
    "DARK_YELLOW": "808000",
    "GRAY_25": "C0C0C0",
    "GRAY_50": "808080",
    "GREEN": "008000",
    "PINK": "FF00FF",
    "RED": "FF0000",
    "TEAL": "008080",
    "TURQUOISE": "00FFFF",
    "VIOLET": "800080",
    "WHITE": "FFFFFF",
    "YELLOW": "FFFF00",
}


def luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _is_large(run: Run, config: RuleConfig) -> bool:
    size = run.size_pt if run.size_pt is not None else config.default_text_pt
    return size >= config.large_text_pt or (run.bold and size >= config.large_bold_pt)


@rule(
    "CLR-001",
    "Text colour contrast is too low",
    Severity.HIGH,
    "1.4.3",
    WcagLevel.AA,
)
def low_contrast(doc: ParsedDocument, config: RuleConfig) -> list[Hit]:
    hits: list[Hit] = []
    for block in doc.blocks:
        for run in block.runs:
            if not run.text.strip():
                continue
            foreground = (run.color_hex or _TEXT_DEFAULT).upper()
            background = _HIGHLIGHTS.get((run.highlight or "").upper(), _PAGE)
            needed = config.contrast_large if _is_large(run, config) else config.contrast_normal
            ratio = contrast_ratio(foreground, background)
            if ratio < needed:
                hits.append(
                    Hit(
                        block,
                        f"Text contrast is {ratio:.1f}:1; at least {needed:g}:1 is needed.",
                        "Use a darker text colour or a lighter background.",
                    )
                )
                break  # one finding per block
    return hits
