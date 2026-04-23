"""Funder matcher for the National Natural Science Foundation of China (NSFC)."""

import re
from pathlib import Path

from .._award import AwardDetailsResult
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "nsfc"
FUNDER_DISPLAY_NAME: str = "National Natural Science Foundation of China"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ()
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ()
FUNDER_OPENALEX_ID: str = "F4320321001"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ()

_NSFC_NUMERIC_RE = re.compile(r"\b\d{7,11}\b")
_NSFC_JOINT_FUND_RE = re.compile(r"\bU\d{7,8}\b")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_NSFC_NUMERIC_RE.search(s) or _NSFC_JOINT_FUND_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    s = normalize_dashes(text)
    # For hyphenated IDs like "20221279-ZKT03", capture only the numeric prefix.
    numeric = [m.group() for m in _NSFC_NUMERIC_RE.finditer(s)]
    joint = [m.group() for m in _NSFC_JOINT_FUND_RE.finditer(s)]
    seen: set[str] = set()
    result: list[str] = []
    for item in numeric + joint:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    # Not implemented: the primary source (kd.nsfc.gov.cn) is DNS-unreachable
    # outside China, and third-party aggregators that do expose an API require
    # paid subscriptions. See plans/nsfc_scraper_spec.md for investigation notes.
    raise NotImplementedError(
        "NSFC get_award_details is not implemented. "
        "The primary portal (kd.nsfc.gov.cn) is inaccessible outside China "
        "and no publicly usable API has been found. "
        "See plans/nsfc_scraper_spec.md."
    )


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/nsfc_scraper_spec.md",
    verified_awards=(),
    matching_ids=(
        # Standard 8-digit NSFC numbers.
        "62206216",
        "91949120",
        "62432006",
        "12202470",
        "62141608",
        "11871183",
        "51501088",
        "61933003",
        # 11-digit international cooperation IDs.
        "61661146007",
        "61711540303",
        # Joint Fund (U-prefix).
        "U1936210",
        # Hyphenated form: numeric prefix is matched even with sub-task suffix.
        "20221279-ZKT03",
    ),
    not_found_awards=(
        # Clearly synthetic 8-digit numbers unlikely to exist in NSFC records.
        "99999999",
        "00000001",
        "12345678",
    ),
    rejected_ids=(
        # Municipal / provincial funds. The internal letter-digit junctions
        # have no word boundary, so the digit run is never matched.
        "JCYJ20210324120011032",
        "YDZX20233100001001",
        # Too few digits.
        "131060",
        "132002",
        # MoST Key R&D Programme — has letters between digit groups, so the
        # numeric portions never have word boundaries on both sides.
        "2021ZD0201405",
        # Cross-funder distractors.
        "EP/S00923X/1",
        "ANR-21-CE29-0003",
    ),
    extraction_texts=(
        ExtractionExample(
            text="Funded by NSFC grants 62206216 and U1936210.",
            expected_extracted=("62206216", "U1936210"),
            verified_existing=(),
        ),
        ExtractionExample(
            text="supported by 61661146007 and 61711540303",
            expected_extracted=("61661146007", "61711540303"),
            verified_existing=(),
        ),
    ),
)
