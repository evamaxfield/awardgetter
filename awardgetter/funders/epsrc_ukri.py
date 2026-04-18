"""Funder matcher for UKRI research councils (EPSRC, MRC, BBSRC, NERC, ESRC, AHRC, STFC)."""

import re

from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "epsrc_ukri"
FUNDER_DISPLAY_NAME: str = "UK Research and Innovation (UKRI) councils"

_UKRI_RE = re.compile(
    r"\b(?:EP|MR|BB|NE|ES|AH|ST|GR)/[A-Z0-9]{6,9}(?:/\d+)?\b"
)


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_UKRI_RE.search(s))
