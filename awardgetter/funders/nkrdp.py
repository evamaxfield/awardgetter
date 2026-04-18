"""Funder matcher for China's National Key Research and Development Program (NKRDP)."""

import re

from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "nkrdp"
FUNDER_DISPLAY_NAME: str = "National Key Research and Development Program of China"

# YYYY + programme code (YFA-YFF, ZD, AAA, QN[RC]) + sequential digits
_NKRDP_RE = re.compile(r"\b\d{4}(?:YF[A-F]|ZD|AAA|QN[A-Z]*)\d+\b")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_NKRDP_RE.search(s))
