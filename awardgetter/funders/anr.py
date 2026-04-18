"""Funder matcher for the French Agence Nationale de la Recherche (ANR)."""

import re

from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "anr"
FUNDER_DISPLAY_NAME: str = "Agence Nationale de la Recherche"

# Standard ANR reference: ANR-YY-XXXX-NNNN(-S), where XXXX is a 2-6 char
# programme code (CE##, JCJC, MRSEI, MPGA, LABX, EQPX, IDEX, INBS, NEUC,
# PCPA, ...).
_ANR_WITH_PREFIX_RE = re.compile(r"\bANR-\d{2}-[A-Z]{2,6}\d*-\d+(?:-\d+)?\b")

# No-prefix form seen in acknowledgements: 10-INBS-09-08, 16-IDEX-0004,
# 20-PCPA-0010. Only accept a closed set of programme codes so we don't
# false-match arbitrary date-like strings.
_ANR_NO_PREFIX_RE = re.compile(
    r"\b\d{2}-(?:LABX|EQPX|IDEX|INBS|NEUC|PCPA|JCJC|MRSEI|MPGA|CE\d+)-\d+(?:-\d+)?\b"
)


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_ANR_WITH_PREFIX_RE.search(s) or _ANR_NO_PREFIX_RE.search(s))
