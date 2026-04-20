"""Funder matcher for China's National Key Research and Development Program (NKRDP)."""

import re
from pathlib import Path

from .._award import AwardDetailsResult
from .._spec import FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "nkrdp"
FUNDER_DISPLAY_NAME: str = "National Key Research and Development Program of China"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ()
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ()

# YYYY + programme code (YFA-YFF, ZD, AAA, QN[RC]) + sequential digits
_NKRDP_RE = re.compile(r"\b\d{4}(?:YF[A-F]|ZD|AAA|QN[A-Z]*)\d+\b")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_NKRDP_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    raise NotImplementedError


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    raise NotImplementedError


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/nkrdp_spec.md",
    verified_awards=(),
    matching_ids=(
        # Sub-project (15-char) IDs.
        "2022ZD0160401",
        "2022ZD0118302",
        "2017YFC0821602",
        "2020YFC2004300",
        "2020YFA0712402",
        "2020YFA0908700",
        "2016YFB1001405",
        "2016YFB1001001",
        "2022YFB3104700",
        "2022YFA1204201",
        "2022YFC3502100",
        "2023YFB4503803",
        "2021ZD0201300",
        # Project-level (13-char) IDs.
        "2020YFF0304100",
        # Science & Technology Innovation 2030 sub-programme (`AAA`).
        "2020AAA0105601",
        "2020AAA0106300",
        # Youth Scientist Programme variant.
        "2021QNRC001",
    ),
    not_found_awards=(),
    rejected_ids=(
        # Possibly a provincial fund — does not match the NKRDP code set.
        "B16003",
        # Truncated — no digits after the programme code.
        "2020YFC",
        # Cross-funder distractors.
        "62206216",
        "EP/S00923X/1",
        "DE-SC0021358",
        "ANR-21-CE29-0003",
    ),
    extraction_texts=(),
)
