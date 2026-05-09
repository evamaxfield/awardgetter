"""Funder matcher for the Office of Naval Research (ONR)."""

import re
from pathlib import Path

from .._award import AwardDetailsResult
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes
from ._usaspending import query_usaspending

FUNDER_ID: str = "onr"
FUNDER_DISPLAY_NAME: str = "Office of Naval Research"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ()
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ("ONR",)
FUNDER_OPENALEX_ID: str = "F4320337345"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ("F4320338298",)  # ONR Global

# Standard ONR grant format:
#   N00014-24-1-2003  (dashed: N00014 - YY - seq - NNNN)
#   N000142012828     (compact, no dashes: N00014 + 7 digits)
#   N0001418IP00037   (inter-agency: N00014 + YY + letters + digits)
# Also matches ONR Global (N62909) and similar Navy activity address codes.
_ONR_N00014_DASHED_RE = re.compile(
    r"\bN00014-\d{2}-(?:\d{1,3}|[A-Z]{1,3}\d{0,3})-\d{4,5}\b",
    re.IGNORECASE,
)
_ONR_N00014_COMPACT_RE = re.compile(
    r"\bN00014[\dA-Z]{7,9}\b",
    re.IGNORECASE,
)
_ONR_N62909_RE = re.compile(
    r"\bN62909[-]\d{2}[-]\d[-]\d{4}\b",
    re.IGNORECASE,
)

# Strip trailing ) that sometimes wraps grant numbers in prose.
_TRAILING_PAREN_RE = re.compile(r"\)+$")


def _normalize_onr(text: str) -> str:
    s = normalize_dashes(text).strip()
    s = _TRAILING_PAREN_RE.sub("", s)
    return s


def check_award_id(text: str) -> bool:
    s = _normalize_onr(text)
    return bool(
        _ONR_N00014_DASHED_RE.search(s)
        or _ONR_N00014_COMPACT_RE.search(s)
        or _ONR_N62909_RE.search(s)
    )


def extract_award_ids(text: str) -> list[str]:
    s = _normalize_onr(text)
    seen: set[str] = set()
    results: list[str] = []
    for pattern in (_ONR_N00014_DASHED_RE, _ONR_N00014_COMPACT_RE, _ONR_N62909_RE):
        for m in pattern.finditer(s):
            val = m.group(0).upper().rstrip(")")
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
        "N00014-24-1-2003",
        "N00014-19-1-2522",
        "N00014-17-1-2895",
        "N00014-16-1-2711",
        "N00014-22-1-2529",
    ),
    matching_ids=(
        # Compact no-dash variants.
        "N000142012828",
        "N000141712058",
        "N000141712310",
        "N000142312670",
        # Inter-agency transfer format.
        "N0001418IP00037",
        # ONR Global.
        "N62909-18-1-2170",
        "N62909-21-1-2042",
        # Trailing paren stripped.
        "N000141712058)",
    ),
    not_found_awards=(),
    rejected_ids=(
        # Air Force Research Laboratory (AFOSR) — not ONR.
        "FA9550-16-1-0231",
        # DOE award.
        "DE-SC0021358",
        # NSF award.
        "1728743",
    ),
    extraction_texts=(
        ExtractionExample(
            text="Supported by ONR grants N00014-24-1-2003 and N00014-22-1-2529.",
            expected_extracted=("N00014-24-1-2003", "N00014-22-1-2529"),
            verified_existing=("N00014-24-1-2003", "N00014-22-1-2529"),
        ),
    ),
)
