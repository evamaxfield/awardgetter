"""Funder matcher for the National Aeronautics and Space Administration (NASA)."""

import re
from pathlib import Path

from .._award import AwardDetailsResult
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes
from ._usaspending import query_usaspending

FUNDER_ID: str = "nasa"
FUNDER_DISPLAY_NAME: str = "National Aeronautics and Space Administration"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ()
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ("NASA",)
FUNDER_OPENALEX_ID: str = "F4320306101"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ()

# Modern ROSES/NSPIRES format post-2017: 80NSSC17K0597, 80NSSC22K1755
_NASA_80NSSC_RE = re.compile(r"\b80NSSC\d{2}[A-Z]\d{3,5}\b", re.IGNORECASE)

# GSFC-specific format: 80GSFC21R0032
_NASA_80GSFC_RE = re.compile(r"\b80GSFC\d{2}[A-Z]\d{3,5}\b", re.IGNORECASE)

# Older pre-2017 format: NNX16AG62G, NNX15AH54G
_NASA_NNX_RE = re.compile(r"\bNNX\d{2}[A-Z]{2}\d{2}[A-Z]\b", re.IGNORECASE)

# ATP (Astrophysics Theory Program) format: 19-ATP19-0051, 21-ATP21-0010
_NASA_ATP_RE = re.compile(r"\b\d{2}-ATP\d{2}-\d{4}\b", re.IGNORECASE)

# Strip leading "ATP " keyword prefix (e.g. "ATP 80NSSC18K101" → "80NSSC18K101").
_ATP_KEYWORD_RE = re.compile(r"^ATP\s+", re.IGNORECASE)


def _normalize_nasa(text: str) -> str:
    s = normalize_dashes(text).strip()
    s = _ATP_KEYWORD_RE.sub("", s)
    return s


def check_award_id(text: str) -> bool:
    s = _normalize_nasa(text)
    return bool(
        _NASA_80NSSC_RE.search(s)
        or _NASA_80GSFC_RE.search(s)
        or _NASA_NNX_RE.search(s)
        or _NASA_ATP_RE.search(s)
    )


def extract_award_ids(text: str) -> list[str]:
    s = _normalize_nasa(text)
    seen: set[str] = set()
    results: list[str] = []
    for pattern in (_NASA_80NSSC_RE, _NASA_80GSFC_RE, _NASA_NNX_RE, _NASA_ATP_RE):
        for m in pattern.finditer(s):
            val = m.group(0).upper()
            if val not in seen:
                seen.add(val)
                results.append(val)
    return results


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    return query_usaspending(award_ids, FUNDER_ID)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    verified_awards=(
        "80NSSC17K0597",
        "80NSSC22K1755",
        "80NSSC19K0626",
        "80NSSC20K0917",
        "NNX16AG62G",
    ),
    matching_ids=(
        "80NSSC22K1163",
        "80NSSC22K0685",
        "80GSFC21R0032",
        "NNX15AH54G",
        "NNX17AC55G",
        "19-ATP19-0051",
        "21-ATP21-0010",
        # "ATP " keyword prefix stripped before matching.
        "ATP 80NSSC18K101",
    ),
    not_found_awards=(),
    rejected_ids=(
        # Bare numbers without NASA-specific prefix.
        "6779",
        "10118",
        # DOE award.
        "DE-SC0021358",
        # NSF award.
        "1728743",
    ),
    extraction_texts=(
        ExtractionExample(
            text="This work was supported by NASA grant 80NSSC17K0597 and NNX16AG62G.",
            expected_extracted=("80NSSC17K0597", "NNX16AG62G"),
            verified_existing=("80NSSC17K0597", "NNX16AG62G"),
        ),
    ),
)
