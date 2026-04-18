"""Funder matcher for the U.S. Department of Energy (DOE)."""

import re
from pathlib import Path

from .._award import AwardDetailsResult
from .._spec import FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "doe"
FUNDER_DISPLAY_NAME: str = "U.S. Department of Energy"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ()
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ("Department of Energy",)

# Matches post-2007 form (DE-SC0021358, DE-OE0000895) and pre-2007 form
# (DE-FG02-87ER40315, DE-AC02-05CH11231). Accepts a missing hyphen after
# "DE" (DEAC05-00OR22725) as seen in real acknowledgements.
_DOE_RE = re.compile(r"\bDE-?[A-Z]{2}\d+(?:-\d{2}[A-Z]{2}\d+)?\b")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_DOE_RE.search(s))


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
    source="plans/doe_spec.md",
    positive=(
        # Post-2007 Office of Science grants.
        "DE-SC0021358",
        "DE-SC0016260",
        "DE-SC0010558",
        "DE-SC0012704",
        "DE-SC0021303",
        "DE-SC0025642",
        "DE-SC0020441",
        # Non-SC offices.
        "DE-OE0000895",
        # Pre-2007 grants.
        "DE-FG02-87ER40315",
        # National-lab M&O contracts.
        "DE-AC02-05CH11231",
        "DE-AC05-00OR22725",
        "DE-AC36-08GO28308",
        "DE-AC02-06CH11357",
        "DE-AC02-76SF00515",
        "DE-AC05-76RL01830",
        # Real-world noise: missing inner dash, trailing punctuation,
        # leading "No. " prefix.
        "DEAC05-00OR22725",
        "DE-AC36-08GO28308.",
        "No. DE-AC02-06CH11357",
    ),
    negative=(
        # BER programme tracking codes — not award numbers.
        "ERKJ335",
        # Numeric-only / label-only inputs.
        "62201",
        "COVID-19",
        # No-prefix form — current matcher requires a literal "DE".
        "SC0022917",
        # Missing "DE" prefix — matcher does not synthesise it.
        "-AC36-08GO28308",
        # Cross-funder distractors.
        "EP/S00923X/1",
        "ANR-21-CE29-0003",
        "2022ZD0160401",
        "62206216",
    ),
)
