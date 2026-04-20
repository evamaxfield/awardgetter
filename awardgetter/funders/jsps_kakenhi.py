"""Funder matcher for JSPS KAKENHI grants."""

import re
from pathlib import Path

from .._award import AwardDetailsResult
from .._spec import FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "jsps_kakenhi"
FUNDER_DISPLAY_NAME: str = "Japan Society for the Promotion of Science (KAKENHI)"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ("jsps", "kakenhi")
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = (
    "Japan Society for the Promotion of Science",
    "KAKENHI",
)
FUNDER_OPENALEX_ID: str = "F4320334764"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ()

# KAKENHI grant number: 2-digit fiscal year + letter code (H/K/J/L/N) +
# 5-digit serial. Optional JP citation prefix. Handles multi-id strings
# like "JP26282221, JP26120733, JP18H04037, and JP20H05955".
_KAKENHI_RE = re.compile(r"\b(?:JP)?\d{2}[HKJLN]\d{5}\b")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_KAKENHI_RE.search(s))


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
    source="plans/jsps_kakenhi_spec.md",
    verified_awards=(),
    matching_ids=(
        # Standard `YY` + letter code + 5-digit serial.
        "24K22291",
        "22H05118",
        "19H01891",
        "19K11852",
        "20H05951",
        "21J20930",
        "18K03693",
        "23H04869",
        "19H03696",
        "24K03119",
        # `JP` citation prefix — handled by the optional `(?:JP)?` group.
        "JP22K17712",
        "JP22H00516",
        # Multi-grant string — one hit is sufficient even when other tokens in
        # the string (e.g. JP26282221) are bare-numeric old-format grants the
        # current matcher does not recognise.
        "KAKENHI Grants JP26282221, JP26120733, JP18H04037, and JP20H05955",
    ),
    not_found_awards=(
        # Serial 99999 is extremely high and won't appear in KAKENHI records.
        "24K99999",
        "22H99999",
        "20N00000",
    ),
    rejected_ids=(
        # JST grants — different funder entirely.
        "JPMJSP2119",
        # Old purely-numeric KAKENHI numbers — not handled by the current regex
        # which requires the H/K/J/L/N letter code in the middle.
        "20002",
        "852010",
        # Truncated / wrong digit count.
        "19K2286",
        # Free-text labels.
        "KAKENHI Grant Number",
        "MEXT KAKENHI",
        "Advanced Research Netwo",
        # Cross-funder distractors.
        "EP/S00923X/1",
        "DE-SC0021358",
    ),
    extraction_texts=(),
)
