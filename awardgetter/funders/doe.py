"""Funder matcher for the U.S. Department of Energy (DOE)."""

import re

from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "doe"
FUNDER_DISPLAY_NAME: str = "U.S. Department of Energy"

# Matches post-2007 form (DE-SC0021358, DE-OE0000895) and pre-2007 form
# (DE-FG02-87ER40315, DE-AC02-05CH11231). Accepts a missing hyphen after
# "DE" (DEAC05-00OR22725) as seen in real acknowledgements.
_DOE_RE = re.compile(
    r"\bDE-?[A-Z]{2}\d+(?:-\d{2}[A-Z]{2}\d+)?\b"
)


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_DOE_RE.search(s))
