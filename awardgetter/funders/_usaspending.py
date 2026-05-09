"""Shared helper for querying the USASpending.gov grants API."""

import time
from datetime import date, datetime

import requests

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason

_USASPENDING_SEARCH_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
_USASPENDING_FIELDS = ["Award ID", "Award Amount", "Start Date", "End Date"]
# Assistance award type codes: grants and cooperative agreements.
_AWARD_TYPE_CODES = ["02", "03", "04", "05"]


def parse_usaspending_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def query_usaspending(award_ids: list[str], funder_id: str) -> AwardDetailsResult:
    """Query USASpending for a list of already-normalised award IDs (FAINs).

    Hyphens are stripped before lookup because USASpending stores FAINs without
    them (e.g. DE-SC0021358 → DESC0021358, N00014-24-1-2003 → N00014241-2003).
    Returns a generic "Not found in USASpending" detail for all not-founds;
    callers may replace this with more specific messaging.
    """
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    for award_id in award_ids:
        fain = award_id.replace("-", "")
        try:
            resp = requests.post(
                _USASPENDING_SEARCH_URL,
                json={
                    "subawards": False,
                    "limit": 1,
                    "fields": _USASPENDING_FIELDS,
                    "filters": {
                        "award_ids": [fain],
                        "award_type_codes": _AWARD_TYPE_CODES,
                    },
                },
                timeout=10,
            )
        except requests.exceptions.RequestException as exc:
            not_found.append(
                AwardNotFound(
                    funder_id=funder_id,
                    input_text=award_id,
                    reason=NotFoundReason.API_ERROR,
                    detail=str(exc),
                )
            )
            continue

        if resp.status_code == 429:
            not_found.append(
                AwardNotFound(
                    funder_id=funder_id,
                    input_text=award_id,
                    reason=NotFoundReason.RATE_LIMITED,
                    detail="HTTP 429",
                )
            )
            continue

        if not resp.ok:
            not_found.append(
                AwardNotFound(
                    funder_id=funder_id,
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
                    funder_id=funder_id,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="Not found in USASpending",
                )
            )
            continue

        row = results[0]
        amount_raw = row.get("Award Amount")
        try:
            amount = float(amount_raw) if amount_raw is not None else None
        except (ValueError, TypeError):
            amount = None

        found.append(
            AwardDetails(
                funder_id=funder_id,
                award_id=award_id,
                amount_funded=amount,
                currency="USD",
                start_date=parse_usaspending_date(row.get("Start Date")),
                end_date=parse_usaspending_date(row.get("End Date")),
            )
        )

        time.sleep(0.5)

    return AwardDetailsResult(found=found, not_found=not_found)
