"""Funder matcher for JSPS KAKENHI grants."""

import os
import random
import re
import time
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._spec import ExtractionExample, FunderExamples
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

_KAKEN_API_URL = "https://kaken.nii.ac.jp/opensearch/"
_KAKEN_APP_ID_ENV = "KAKEN_APP_ID"
# KAKEN API docs warn against high-volume access; 1.5s + jitter is conservative.
_KAKEN_RATE_LIMIT_SLEEP = 1.5


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_KAKENHI_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    s = normalize_dashes(text)
    raw = _KAKENHI_RE.findall(s)
    # Strip the JP citation prefix; the bare 8-char number is the API lookup key.
    return [r[2:] if r.startswith("JP") else r for r in raw]


def _get_app_id() -> str:
    # Load env
    load_dotenv()

    app_id = os.environ.get(_KAKEN_APP_ID_ENV, "")
    if not app_id:
        raise ValueError(
            f"KAKEN API requires a free Application ID. "
            f"Register at https://support.nii.ac.jp/en/cinii/api/developer "
            f"and set the {_KAKEN_APP_ID_ENV} environment variable."
        )
    return app_id


def _fy_start_date(fy: str) -> date:
    """Japanese fiscal year start: April 1 of the given year."""
    return date(int(fy), 4, 1)


def _fy_end_date(fy: str) -> date:
    """Japanese fiscal year end: March 31 of the following year."""
    return date(int(fy) + 1, 3, 31)


def _extract_scalar(value: object) -> str | None:
    """Unwrap a JSON-LD @value dict or return a plain string/int as-is."""
    if isinstance(value, dict):
        return str(value.get("@value", "")) or None
    if value is not None:
        return str(value)
    return None


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    try:
        app_id = _get_app_id()
    except ValueError as exc:
        return AwardDetailsResult(
            found=[],
            not_found=[
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=aid,
                    reason=NotFoundReason.API_ERROR,
                    detail=str(exc),
                )
                for aid in award_ids
            ],
        )

    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    for i, award_id in enumerate(award_ids):
        if i > 0:
            time.sleep(_KAKEN_RATE_LIMIT_SLEEP + random.uniform(0.0, 0.5))

        # Strip JP citation prefix for the lookup key.
        lookup_id = award_id[2:] if award_id.startswith("JP") else award_id

        try:
            resp = requests.get(
                _KAKEN_API_URL,
                params={"kenkyuuKadaiKiban": lookup_id, "appid": app_id, "format": "json"},
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

        try:
            data = resp.json()
        except ValueError:
            print(resp)
            print(resp.content)
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.PARSE_ERROR,
                    detail="Non-JSON response from KAKEN API",
                )
            )
            continue

        # OpenSearch totalResults — may be a plain string or a JSON-LD {"@value": "N"} dict.
        total_raw = data.get("opensearch:totalResults", data.get("totalResults", "0"))
        total_str = _extract_scalar(total_raw) or "0"
        if int(total_str) == 0:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="No results in KAKEN database",
                )
            )
            continue

        try:
            items = data.get("items", [])
            if not items:
                raise KeyError("items")
            item = items[0]

            # Funding amount in JPY — try field name variants across API versions.
            amount: float | None = None
            for key in ("kaken:totalBudget", "kaken:totalAmount", "kaken:grantAmount"):
                raw = item.get(key)
                if raw is not None:
                    scalar = _extract_scalar(raw)
                    if scalar:
                        try:
                            amount = float(scalar.replace(",", ""))
                        except ValueError:
                            pass
                    break

            # Fiscal year fields — KAKEN uses Japanese FY (April-March).
            start_fy: str | None = None
            end_fy: str | None = None
            for key in ("kaken:startYear", "kaken:firstYear", "kaken:fiscalStartYear"):
                v = _extract_scalar(item.get(key))
                if v:
                    start_fy = v
                    break
            for key in ("kaken:endYear", "kaken:lastYear", "kaken:fiscalEndYear"):
                v = _extract_scalar(item.get(key))
                if v:
                    end_fy = v
                    break

        except (KeyError, IndexError, TypeError, ValueError) as exc:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.PARSE_ERROR,
                    detail=f"Unexpected KAKEN response structure: {exc}",
                )
            )
            continue

        found.append(
            AwardDetails(
                funder_id=FUNDER_ID,
                award_id=award_id,
                amount_funded=amount,
                currency="JPY",
                start_date=_fy_start_date(start_fy) if start_fy else None,
                end_date=_fy_end_date(end_fy) if end_fy else None,
            )
        )

    return AwardDetailsResult(found=found, not_found=not_found)


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
    extraction_texts=(
        # Standard IDs — bare 8-char returned (no JP prefix).
        ExtractionExample(
            text="22H05118 and 19K11852",
            expected_extracted=("22H05118", "19K11852"),
            verified_existing=(),
        ),
        # JP-prefixed IDs — prefix stripped in output.
        ExtractionExample(
            text="supported by JSPS KAKENHI JP22K17712 and JP22H00516",
            expected_extracted=("22K17712", "22H00516"),
            verified_existing=(),
        ),
        # Multi-grant string — only the letter-code IDs are extracted;
        # purely-numeric old-format IDs (JP26282221, JP26120733) are skipped.
        ExtractionExample(
            text="KAKENHI Grants JP26282221, JP26120733, JP18H04037, and JP20H05955",
            expected_extracted=("18H04037", "20H05955"),
            verified_existing=(),
        ),
    ),
)
