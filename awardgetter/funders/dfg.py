"""Funder matcher for the Deutsche Forschungsgemeinschaft (DFG)."""

import re

from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "dfg"
FUNDER_DISPLAY_NAME: str = "Deutsche Forschungsgemeinschaft"

# Distinctive DFG programme codes only. Purely numeric GEPRIS project IDs
# are intentionally not matched here because they overlap with NSF/NSFC/
# CORDIS — callers with explicit DFG context should pass the funder
# directly rather than infer from a bare numeric string.
_DFG_RE = re.compile(
    r"\b(?:SFB-?TRR|SFB|TRR|FOR|EXC|GRK|RTG|SPP|INST)\s*\d+\b",
    re.IGNORECASE,
)


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_DFG_RE.search(s))
