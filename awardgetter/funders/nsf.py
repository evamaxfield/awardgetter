"""Funder matcher for the U.S. National Science Foundation (NSF)."""

import re

from .._spec import FunderExamples
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


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="awardgetter/funders/nsf.py (no plan file)",
    positive=(
        # Bare 7-digit NSF award IDs.
        "2034901",
        "1956322",
        # NSF agency word is stripped, then 7-digit match.
        "NSF-1956322",
        "NSF 2034901",
        # Generic surrounding text.
        "Award #1956322",
        # Internal whitespace within the 7 digits is collapsed.
        "NSF 19 56322",
    ),
    negative=(
        # Wrong digit counts.
        "62206216",
        "131060",
        # Cross-funder distractors.
        "EP/S00923X/1",
        "ANR-21-CE29-0003",
        "DE-SC0021358",
        "2022ZD0160401",
    ),
)
