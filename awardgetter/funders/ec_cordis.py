"""Funder matcher for European Commission research projects (CORDIS)."""

import re

from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "ec_cordis"
FUNDER_DISPLAY_NAME: str = "European Commission (CORDIS)"

# CORDIS numeric project IDs range from ~6 digits (FP6/FP7) to 9 digits
# (Horizon Europe). Intentionally overlaps with NSF/NSFC for pure numerics.
_CORDIS_NUMERIC_RE = re.compile(r"\b\d{6,9}\b")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_CORDIS_NUMERIC_RE.search(s))
