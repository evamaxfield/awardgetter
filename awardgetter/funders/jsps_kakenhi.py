"""Funder matcher for JSPS KAKENHI grants."""

import re

from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "jsps_kakenhi"
FUNDER_DISPLAY_NAME: str = "Japan Society for the Promotion of Science (KAKENHI)"

# KAKENHI grant number: 2-digit fiscal year + letter code (H/K/J/L/N) +
# 5-digit serial. Optional JP citation prefix. Handles multi-id strings
# like "JP26282221, JP26120733, JP18H04037, and JP20H05955".
_KAKENHI_RE = re.compile(r"\b(?:JP)?\d{2}[HKJLN]\d{5}\b")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_KAKENHI_RE.search(s))
