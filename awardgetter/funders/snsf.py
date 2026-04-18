"""Funder matcher for the Swiss National Science Foundation (SNSF)."""

import re

from .._spec import FunderExamples
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


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/snsf_spec.md",
    positive=(
        # Programme-prefixed grant numbers.
        "PZ00P3_180085",
        "PDFMP3-130309",
        "51NF40_225155",
        "200021_181978/1",
        "CRSII5_205975",
        "IZRJZ3_164171",
        "200021_166275",
        "PP00P2_138979",
        "200021_20484",
        "200021L_212718",
        "CR22I2_166110",
        "P400PB_199242",
        # Leading `#` is stripped.
        "#51NF40_180888",
        # Embedded in a descriptive label.
        "Prospective Researcher Fellowship, PBZHP2-147259",
    ),
    negative=(
        # Programme umbrellas — not single grants.
        "NRP-77",
        "SNSF-ERC",
        "multiple",
        # Bare older-format numeric IDs are not handled by the current matcher
        # (it requires a programme prefix). Documented gap.
        "192079",
        "178220",
        "955606",
        # Cross-funder distractors.
        "EP/S00923X/1",
        "DE-SC0021358",
        "ANR-21-CE29-0003",
    ),
)
