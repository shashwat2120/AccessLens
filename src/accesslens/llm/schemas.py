"""Structured output the LLM must produce. Anything else fails validation and is dropped."""

from typing import Literal

from pydantic import BaseModel, Field

# The only rules the LLM may speak about (TRD §5). It never picks the rule itself: we set the
# rule per item and discard answers whose rule_id differs.
LlmRuleId = Literal["IMG-003", "LNK-003", "TXT-006", "TXT-001", "TXT-002"]


MAX_RESULTS = 50  # a batch never holds more items than this; extra answers are ignored


class ItemResult(BaseModel):
    item_id: str = Field(max_length=40)
    rule_id: LlmRuleId
    issue: bool
    confidence: float = Field(ge=0.0, le=1.0)
    message: str = Field(max_length=300)
    suggestion: str = Field(max_length=500)


class BatchResult(BaseModel):
    # No maxItems here: Gemini's structured-output mode rejects that keyword with a vague
    # "invalid argument". The cap is enforced in code instead (MAX_RESULTS, see checks.py).
    results: list[ItemResult]
