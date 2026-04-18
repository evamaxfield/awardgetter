"""Funder matcher for the U.S. National Science Foundation (NSF)."""

import re

from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "nsf"
FUNDER_DISPLAY_NAME: str = "U.S. National Science Foundation"

_NSF_WORD_RE = re.compile(r"\bNSF\b", re.IGNORECASE)
_DIGIT_SEPARATOR_DIGIT_RE = re.compile(r"(\d)[\s\-]+(\d)")
_NSF_AWARD_ID_RE = re.compile(r"\b\d{7}\b")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    s = _NSF_WORD_RE.sub(" ", s)
    s = _DIGIT_SEPARATOR_DIGIT_RE.sub(r"\1\2", s)
    return bool(_NSF_AWARD_ID_RE.search(s))
