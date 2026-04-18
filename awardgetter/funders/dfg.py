"""Funder matcher for the Deutsche Forschungsgemeinschaft (DFG)."""

import re
from pathlib import Path

from .._award import AwardDetailsResult
from .._spec import FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "dfg"
FUNDER_DISPLAY_NAME: str = "Deutsche Forschungsgemeinschaft"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ("dfg",)
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ("German Research Foundation",)

# Distinctive DFG programme codes only. Purely numeric GEPRIS project IDs
# are intentionally not matched here because they overlap with NSF/NSFC/
# CORDIS — callers with explicit DFG context should pass the funder
# directly rather than infer from a bare numeric string.
_DFG_RE = re.compile(
    r"\b(?:SFB-?TRR|SFB|TRR|FOR|EXC|GRK|RTG|SPP|INST)\s*\d+\b",
    re.IGNORECASE,
)


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_DFG_RE.search(s))


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
    source="plans/dfg_gepris_spec.md",
    positive=(
        # Programme acronym + number; sub-project suffixes are tolerated.
        "SFB1114/A04",
        "SFB1423 / 421152132 - A07",
        "SFB-TRR 358/1 2023-491392403",
        "SFB 1423",
        "EXC 2067/1 (MBExC)",
        "RTG 2070",
        "FOR 2975",
        "GRK2224",
        "SPP 2363",
        "INST 35/1134-1 FUGG",
    ),
    negative=(
        # Bare GEPRIS numeric IDs — explicitly excluded by the DFG matcher to
        # avoid colliding with NSF/NSFC/CORDIS. See awardgetter/funders/dfg.py.
        "39087428",
        "455548460",
        "460037581",
        "396611854",
        "460247524",
        # PI-style citation references — not GEPRIS programme codes.
        "HE 6166/17-1",
        "2315/11-1",
        # Free-text labels.
        "Deutsche Forschungsgemeinschaft (DFG)",
        "ORIGINS",
        # `BR` is not in the DFG programme alternation.
        "AFFA (BR 5207/1 and NI 369/15)",
        # Cross-funder distractors.
        "EP/S00923X/1",
        "DE-SC0021358",
        "ANR-21-CE29-0003",
    ),
)
