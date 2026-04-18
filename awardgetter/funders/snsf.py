"""Funder matcher for the Swiss National Science Foundation (SNSF)."""

import re

from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "snsf"
FUNDER_DISPLAY_NAME: str = "Swiss National Science Foundation"

# Covers known SNSF programme prefixes (Project Funding, NCCR, Sinergia,
# PRIMA, Ambizione, Postdoc Mobility, Early Postdoc Mobility, international,
# collaborative) followed by an underscore- or dash-separated number.
_SNSF_RE = re.compile(
    r"\b(?:"
    r"200021L?|200020|51NF40|CRSII\d?|PP00P\d?|PZ00P\d?|PDFMP\d?"
    r"|PBZHP\d?|P\d{3}[A-Z]+|IZ[A-Z]+\d*|CR\d+I\d*"
    r")[_-]?\d+\b"
)


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    s = s.lstrip("#")
    return bool(_SNSF_RE.search(s))
