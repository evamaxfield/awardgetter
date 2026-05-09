"""Funder matcher for China's National Key Research and Development Program (NKRDP)."""

import re
from pathlib import Path

from .._award import AwardDetailsResult
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "nkrdp"
FUNDER_DISPLAY_NAME: str = "National Key Research and Development Program of China"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ()
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ()
FUNDER_OPENALEX_ID: str = "F4320335777"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ()

# YYYY + programme code (YFA-YFF, ZD, AAA, QN[RC]) + sequential digits
_NKRDP_RE = re.compile(r"\b\d{4}(?:YF[A-F]|ZD|AAA|QN[A-Z]*)\d+\b")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_NKRDP_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    s = normalize_dashes(text)
    seen: set[str] = set()
    result: list[str] = []
    for m in _NKRDP_RE.finditer(s):
        item = m.group()
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    # Not implemented: the official MoST portal (service.most.gov.cn) requires
    # authentication for project detail lookups, and the third-party aggregator
    # (funresearch.cn) that indexes NKRDP data requires a paid subscription.
    raise NotImplementedError(
        "NKRDP get_award_details is not implemented. "
        "The official MoST portal (service.most.gov.cn) requires login, "
        "and no publicly accessible API has been found."
    )


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
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
    not_found_awards=(
        # Year 2099 is far-future and won't exist in NKRDP records.
        "2099ZD9999999",
        "2099YFA9999999",
        "2099AAA9999",
    ),
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
    extraction_texts=(
        ExtractionExample(
            text="funded by NKRD grants 2022ZD0160401 and 2020YFA0712402",
            expected_extracted=("2022ZD0160401", "2020YFA0712402"),
            verified_existing=(),
        ),
        ExtractionExample(
            text="This work was supported by 2020AAA0105601 and 2021QNRC001.",
            expected_extracted=("2020AAA0105601", "2021QNRC001"),
            verified_existing=(),
        ),
    ),
)
