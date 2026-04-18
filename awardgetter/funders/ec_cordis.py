"""Funder matcher for European Commission research projects (CORDIS)."""

import re

from .._spec import FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "ec_cordis"
FUNDER_DISPLAY_NAME: str = "European Commission (CORDIS)"

# CORDIS numeric project IDs range from ~6 digits (FP6/FP7) to 9 digits
# (Horizon Europe). Intentionally overlaps with NSF/NSFC for pure numerics.
_CORDIS_NUMERIC_RE = re.compile(r"\b\d{6,9}\b")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_CORDIS_NUMERIC_RE.search(s))


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/ec_cordis_spec.md",
    positive=(
        # Numeric CORDIS project IDs (6-9 digits, FP6 through Horizon Europe).
        "101069595",
        "101001318",
        "602150",
        "948381",
        # 6-digit IDs are valid CORDIS but the NSFC plan classifies the same
        # length as `unknown_short`. CORDIS owns 6-digit numerics here.
        "131060",
    ),
    negative=(
        # Acronyms — handled as low-confidence lookups in the spec, but not by
        # the current numeric-only matcher.
        "NEXTGENE",
        "GO-DS21",
        # Programme / call codes.
        "H2020-SC1",
        "H2020-MSCA-IF",
        "H2020RIA",
        "H2020-MSCA-IF-2020",
        "-MSCA-RISE-",
        # Programme names and external funder DOIs.
        "Destination Earth",
        "European Fund for Regional Development",
        "AEI/10.13039/501100011033",
        # Too short.
        "12345",
    ),
)
