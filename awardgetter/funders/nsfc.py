"""Funder matcher for the National Natural Science Foundation of China (NSFC)."""

import re

from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "nsfc"
FUNDER_DISPLAY_NAME: str = "National Natural Science Foundation of China"

_NSFC_NUMERIC_RE = re.compile(r"\b\d{7,11}\b")
_NSFC_JOINT_FUND_RE = re.compile(r"\bU\d{7,8}\b")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_NSFC_NUMERIC_RE.search(s) or _NSFC_JOINT_FUND_RE.search(s))
