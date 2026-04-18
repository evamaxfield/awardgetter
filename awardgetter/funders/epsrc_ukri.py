"""Funder matcher for UKRI research councils (EPSRC, MRC, BBSRC, NERC, ESRC, AHRC, STFC)."""

import re

from .._spec import FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "epsrc_ukri"
FUNDER_DISPLAY_NAME: str = "UK Research and Innovation (UKRI) councils"

_UKRI_RE = re.compile(r"\b(?:EP|MR|BB|NE|ES|AH|ST|GR)/[A-Z0-9]{6,9}(?:/\d+)?\b")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_UKRI_RE.search(s))


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/epsrc_gtr_spec.md",
    positive=(
        # Standard EPSRC references with `/N` suffix.
        "EP/S00923X/1",
        "EP/I013067/1",
        "EP/P020259/1",
        "EP/S022961/1",
        "EP/V002856/1",
        "EP/M025179/1",
        # Incomplete — missing trailing `/N`.
        "EP/L01663X",
        "EP/L016508",
        # Trailing-slash and trailing-paren tolerated by the word-boundary regex.
        "EP/R513295/",
        "EP/P020259/1)",
        # Embedded in surrounding text or multi-grant strings.
        "MVSE EP/V002856/1",
        "EP/I013067/1 and EP/M025179/1",
    ),
    negative=(
        # Wellcome Trust — not part of UKRI.
        "WT101957",
        "WT203148/Z/16/Z",
        # Older format references not in the council-prefix alternation.
        "M009521/1",
        "P008739/1",
        "F500385/1",
        "K000128",
        # Free-text labels and external funder names.
        "CoMPLEX PhD studentship",
        "PhD Scholarship",
        "Mathematics",
        "Programme grant",
        "Not applicable",
        "NVIDIA",
        # Cross-funder distractors.
        "ANR-21-CE29-0003",
        "DE-SC0021358",
        "62206216",
    ),
)
