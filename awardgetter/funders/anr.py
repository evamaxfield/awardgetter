"""Funder matcher for the French Agence Nationale de la Recherche (ANR)."""

import re
from pathlib import Path

from .._award import AwardDetailsResult
from .._spec import FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "anr"
FUNDER_DISPLAY_NAME: str = "Agence Nationale de la Recherche"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ()
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ("Agence nationale de la recherche",)

# Standard ANR reference: ANR-YY-XXXX-NNNN(-S), where XXXX is a 2-6 char
# programme code (CE##, JCJC, MRSEI, MPGA, LABX, EQPX, IDEX, INBS, NEUC,
# PCPA, ...).
_ANR_WITH_PREFIX_RE = re.compile(r"\bANR-\d{2}-[A-Z]{2,6}\d*-\d+(?:-\d+)?\b")

# No-prefix form seen in acknowledgements: 10-INBS-09-08, 16-IDEX-0004,
# 20-PCPA-0010. Only accept a closed set of programme codes so we don't
# false-match arbitrary date-like strings.
_ANR_NO_PREFIX_RE = re.compile(
    r"\b\d{2}-(?:LABX|EQPX|IDEX|INBS|NEUC|PCPA|JCJC|MRSEI|MPGA|CE\d+)-\d+(?:-\d+)?\b"
)


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_ANR_WITH_PREFIX_RE.search(s) or _ANR_NO_PREFIX_RE.search(s))


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
    source="plans/anr_spec.md",
    positive=(
        # Standard ANR competitive grants (DGDS) — `ANR-YY-CExx-NNNN[-S]`.
        "ANR-21-CE29-0003",
        "ANR-17-CE32-0006",
        "ANR-19-CE39-0007",
        "ANR-17-CE23-0012",
        "ANR-19-CE45-0010",
        "ANR-21-CE23-0006",
        "ANR-19-NEUC-0004",
        "ANR-18-CE40-0005",
        # PIA / France 2030 grants — `ANR-YY-PROG-NNNN[-S]`.
        "ANR-10-LABX-12-0",
        "ANR-10-LABX-24",
        "ANR-10-EQPX-29-0",
        "ANR-10-EQPX-03",
        "ANR-11-INBS-0013",
        "ANR-10-INBS-09-08",
        # No-prefix forms seen in acknowledgements.
        "10-INBS-09-08",
        "16-IDEX-0004",
        "20-PCPA-0010",
        # Multi-grant strings: a single hit anywhere in the text is sufficient.
        "ANR-10-EQPX-03 (Equipex) and ANR-10-INBS-09-08 (France Genomique Consortium)",
        "ANR GraVa ANR-18-CE40-0005",
    ),
    negative=(
        # Acronym-only references — not resolvable as ANR IDs.
        "CogFinAIgent",
        "OceaniX",
        # Truncated reference (no project number).
        "ANR-17-MPGA-",
        # Informal spacing — the current matcher does not normalise whitespace.
        "ANR10 LABX56",
        # Cross-funder distractors.
        "EP/S00923X/1",
        "DE-SC0021358",
        "62206216",
        "2022ZD0160401",
        "R01HL123456",
    ),
)
