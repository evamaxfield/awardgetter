"""Funder matcher for the U.S. Department of Energy (DOE)."""

import re
import time
from datetime import datetime
from pathlib import Path

import requests

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
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

# Management & Operating contracts: DE-AC{NN}-{YY}{XX}{NNNNN}
# These are lab-wide umbrella contracts, not individual research grants.
_DOE_MO_RE = re.compile(r"^DE-AC\d{2}-\d{2}[A-Z]{2}\d+$")

_USASPENDING_SEARCH_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
_USASPENDING_FIELDS = [
    "Award ID",
    "total_obligation",
    "period_of_performance_start_date",
    "period_of_performance_current_end_date",
]


def _parse_doe_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_DOE_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    s = normalize_dashes(text)
    seen: set[str] = set()
    results: list[str] = []
    for m in _DOE_RE.finditer(s):
        val = m.group(0).rstrip(".")
        # Normalize missing hyphen: DEAC... -> DE-AC...
        if val.upper().startswith("DE") and len(val) > 2 and val[2] != "-":
            val = "DE-" + val[2:]
        if val not in seen:
            seen.add(val)
            results.append(val)
    return results


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    for award_id in award_ids:
        if _DOE_MO_RE.match(award_id):
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="M&O contract (lab-wide umbrella contract, not an individual grant)",
                )
            )
            continue

        try:
            resp = requests.post(
                _USASPENDING_SEARCH_URL,
                json={
                    "subawards": False,
                    "limit": 1,
                    "fields": _USASPENDING_FIELDS,
                    "filters": {"award_ids": [award_id]},
                },
                timeout=10,
            )
        except requests.exceptions.RequestException as exc:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.API_ERROR,
                    detail=str(exc),
                )
            )
            continue

        if resp.status_code == 429:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.RATE_LIMITED,
                    detail="HTTP 429",
                )
            )
            continue

        if not resp.ok:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.API_ERROR,
                    detail=f"HTTP {resp.status_code}",
                )
            )
            continue

        results = resp.json().get("results") or []
        if not results:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="Not found in USASpending",
                )
            )
            continue

        row = results[0]
        amount_raw = row.get("total_obligation")
        try:
            amount = float(amount_raw) if amount_raw is not None else None
        except (ValueError, TypeError):
            amount = None

        found.append(
            AwardDetails(
                funder_id=FUNDER_ID,
                award_id=award_id,
                amount_funded=amount,
                currency="USD",
                start_date=_parse_doe_date(row.get("period_of_performance_start_date")),
                end_date=_parse_doe_date(row.get("period_of_performance_current_end_date")),
            )
        )

        time.sleep(0.5)

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/doe_spec.md",
    positive=(
        # Post-2007 Office of Science grants — resolvable via USASpending search.
        "DE-SC0021358",
        "DE-SC0016260",
        "DE-SC0010558",
        "DE-SC0012704",
        "DE-SC0021303",
        "DE-SC0025642",
        "DE-SC0020441",
        # Non-SC offices — resolvable via USASpending search.
        "DE-OE0000895",
        # Pre-2007 grants and M&O contracts below are recognized by check_award_id
        # but cannot be resolved by get_award_details. See doe-issues.md.
        # "DE-FG02-87ER40315",
        # "DE-AC02-05CH11231",
        # "DE-AC05-00OR22725",
        # "DE-AC36-08GO28308",
        # "DE-AC02-06CH11357",
        # "DE-AC02-76SF00515",
        # "DE-AC05-76RL01830",
        # "DEAC05-00OR22725",
        # "DE-AC36-08GO28308.",
        # "No. DE-AC02-06CH11357",
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
