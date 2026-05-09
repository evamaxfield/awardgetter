"""Funder matcher for the Australian Research Council (ARC)."""

import re
import time
from datetime import date, datetime
from pathlib import Path

import requests

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "arc"
FUNDER_DISPLAY_NAME: str = "Australian Research Council"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ()
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ("ARC",)
FUNDER_OPENALEX_ID: str = "F4320334704"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ()

# Two-letter program prefix + 9 digits.
# Known prefixes: DP (Discovery Projects), DE (Discovery Early Career), FT (Future Fellowships),
# FL (Laureate Fellowships), LP (Linkage Projects), CE (Centres of Excellence),
# SR (Special Research Initiatives), IC (Industrial Transformation), GT (Grants to Institutions),
# IN (ITTC), LE (Linkage Infrastructure), CR (Collaborative Research Networks).
_ARC_RE = re.compile(
    r"\b(?:DP|DE|FT|FL|LP|CE|SR|IC|GT|IN|LE|CR|MI)\d{7,9}\b",
    re.IGNORECASE,
)

_ARC_API_URL = "https://dataportal.arc.gov.au/NCGP/API/grants/{ref}"
_ARC_RATE_LIMIT_SLEEP = 1.0


def _parse_arc_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def check_award_id(text: str) -> bool:
    return bool(_ARC_RE.search(normalize_dashes(text)))


def extract_award_ids(text: str) -> list[str]:
    s = normalize_dashes(text)
    seen: set[str] = set()
    results: list[str] = []
    for m in _ARC_RE.finditer(s):
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
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    for award_id in award_ids:
        try:
            resp = requests.get(
                _ARC_API_URL.format(ref=award_id.upper()),
                headers={"Accept": "application/json"},
                timeout=30,
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
            time.sleep(_ARC_RATE_LIMIT_SLEEP)
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
                    reason=NotFoundReason.NOT_FOUND
                    if resp.status_code == 404
                    else NotFoundReason.API_ERROR,
                    detail=f"HTTP {resp.status_code}",
                )
            )
            time.sleep(_ARC_RATE_LIMIT_SLEEP)
            continue

        data = resp.json().get("data") or {}
        errors = resp.json().get("errors")
        if errors or not data:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="Not found in ARC Data Portal",
                )
            )
            time.sleep(_ARC_RATE_LIMIT_SLEEP)
            continue

        attrs = data.get("attributes") or {}
        amount_raw = attrs.get("funding-current")
        try:
            amount = float(amount_raw) if amount_raw is not None else None
        except (ValueError, TypeError):
            amount = None

        found.append(
            AwardDetails(
                funder_id=FUNDER_ID,
                award_id=award_id,
                amount_funded=amount,
                currency="AUD",
                start_date=_parse_arc_date(attrs.get("project-start-date")),
                end_date=_parse_arc_date(attrs.get("anticipated-end-date")),
            )
        )
        time.sleep(_ARC_RATE_LIMIT_SLEEP)

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    verified_awards=(
        "DP180103155",
        "FT200100871",
        "DE140100080",
        "DP220101727",
        "FL240100217",
    ),
    matching_ids=(
        "DE210101056",
        "DP150101339",
        "DP130102691",
        "FT200100375",
        "DP170101147",
        "FT190100525",
        "DP160101960",
        "FL180100109",
        "DP200102927",
        "FT110100057",
        "FL17010002",
    ),
    not_found_awards=(),
    rejected_ids=(
        # Bare 9-digit number without program prefix — not resolvable via ARC API.
        "180100741",
        # DOE award.
        "DE-SC0021358",
        # CORDIS number (6-digit).
        "821010",
    ),
    extraction_texts=(
        ExtractionExample(
            text="This research was supported by ARC grants DP180103155 and FT200100871.",
            expected_extracted=("DP180103155", "FT200100871"),
            verified_existing=("DP180103155", "FT200100871"),
        ),
    ),
)
