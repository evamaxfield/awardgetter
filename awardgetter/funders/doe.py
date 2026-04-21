"""Funder matcher for the U.S. Department of Energy (DOE)."""

import re
import time
from datetime import datetime
from pathlib import Path

import requests

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "doe"
FUNDER_DISPLAY_NAME: str = "U.S. Department of Energy"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ()
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ("Department of Energy",)
FUNDER_OPENALEX_ID: str = "F4320306084"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ()

# Matches post-2007 form (DE-SC0021358, DE-OE0000895) and pre-2007 form
# (DE-FG02-87ER40315, DE-AC02-05CH11231). Accepts a missing hyphen after
# "DE" (DEAC05-00OR22725) as seen in real acknowledgements. The optional
# group allows an extra hyphen before the site code (DE-AC02-05-CH11231)
# and 2-3 letter site codes (DE-AC06-76RLO1830).
_DOE_RE = re.compile(r"\bDE-?[A-Z]{2}-?\d+(?:-\d{2,3}-?[A-Z]{2,3}\d+)?\b", re.IGNORECASE)

# Normalise "DOE-..." → "DE-..." before matching (DOE is not the contract prefix).
_DOE_PREFIX_RE = re.compile(r"\bDOE-", re.IGNORECASE)

# Strips "No." / "No. " prefix sometimes written before DOE award numbers.
_NO_PREFIX_RE = re.compile(r"^\s*[Nn]o\.?\s+")

# Management & Operating contracts: DE-AC{NN}-{YY}{XX}{NNNNN}
# These are lab-wide umbrella contracts, not individual research grants.
_DOE_MO_RE = re.compile(r"^DE-AC\d{2}-\d{2}[A-Z]{2}\d+$")

_USASPENDING_SEARCH_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
_USASPENDING_FIELDS = ["Award ID", "Award Amount", "Start Date", "End Date"]
# Assistance award type codes (grants and cooperative agreements).
# award_type_codes is now a required filter field in the USASpending API.
_DOE_AWARD_TYPE_CODES = ["02", "03", "04", "05"]

# OSTI public records API — no auth required. Used to confirm pre-2007 grants exist
# when USASpending has no record of them.
_OSTI_RECORDS_URL = "https://www.osti.gov/api/v1/records"
# Pre-2007 DE-FG* form: DE-FG02-87ER40315
_DOE_PRE2007_RE = re.compile(r"^DE-FG\d{2}-\d{2}[A-Z]{2}\d+$")


def _osti_confirms_pre2007(award_id: str) -> bool:
    osti_key = award_id.removeprefix("DE-")
    try:
        resp = requests.get(
            _OSTI_RECORDS_URL,
            params={"q": osti_key, "rows": 1},
            timeout=10,
        )
        data = resp.json()
        records = data if isinstance(data, list) else (data.get("records") or [])
        return bool(resp.ok and records)
    except requests.exceptions.RequestException:
        return False


def _parse_doe_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _normalize_doe(text: str) -> str:
    s = normalize_dashes(text)
    s = _NO_PREFIX_RE.sub("", s)
    s = _DOE_PREFIX_RE.sub("DE-", s)
    return s


def check_award_id(text: str) -> bool:
    return bool(_DOE_RE.search(_normalize_doe(text)))


def extract_award_ids(text: str) -> list[str]:
    s = _normalize_doe(text)
    seen: set[str] = set()
    results: list[str] = []
    for m in _DOE_RE.finditer(s):
        val = m.group(0).upper().rstrip(".")
        # Normalize missing hyphen: DEAC... -> DE-AC...
        if val.startswith("DE") and len(val) > 2 and val[2] != "-":
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

        # USASpending stores FAINs without hyphens (DE-SC0021358 → DESC0021358).
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
                        "award_type_codes": _DOE_AWARD_TYPE_CODES,
                    },
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
            if _DOE_PRE2007_RE.match(award_id) and _osti_confirms_pre2007(award_id):
                detail = (
                    "Pre-2007 grant confirmed in OSTI"
                    " (financial data not available via public APIs)"
                )
            elif _DOE_PRE2007_RE.match(award_id):
                detail = "Not found in USASpending or OSTI"
            else:
                detail = "Not found in USASpending"
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail=detail,
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
                funder_id=FUNDER_ID,
                award_id=award_id,
                amount_funded=amount,
                currency="USD",
                start_date=_parse_doe_date(row.get("Start Date")),
                end_date=_parse_doe_date(row.get("End Date")),
            )
        )

        time.sleep(0.5)

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/doe_spec.md",
    verified_awards=(
        # Post-2007 Office of Science grants — confirmed via USASpending search.
        "DE-SC0021358",
        "DE-SC0016260",
        "DE-SC0010558",
        "DE-SC0021303",
        "DE-SC0025642",
        "DE-SC0020441",
        # Non-SC office — confirmed via USASpending search.
        "DE-OE0000895",
        # Pre-2007 grant
        "DE-FG02-87ER40315",
        # Lowercase input — normalised to uppercase before lookup;
        # grant confirmed in USASpending.
        "de-sc0011090",
        # Extra hyphen
        "DE-AR-0001282",
        "DE-SC-0022260",
    ),
    matching_ids=(
        "DE-SC0010558",
        "DE-SC0021303",
        "DE-SC0025642",
        "DE-SC0020441",
    ),
    not_found_awards=(
        # M&O umbrella contracts: format-valid but intentionally not individual grants.
        "DE-AC02-05CH11231",
        "DE-AC05-00OR22725",
        # M&O variant with missing DE- hyphen -- normalize_dashes handles it.
        "DEAC05-00OR22725",
        # Extra hyphen before site code — now accepted by extended regex.
        "DE-AC02-05-CH11231",
        # 3-letter site code (RLO = PNNL).
        "DE-AC06-76RLO1830",
        # "No." prefix stripped before matching.
        "No. DE-AC02-05-CH11231",
        # DOE- prefix normalised to DE-.
        "DOE-AC02-05CH11231",
    ),
    rejected_ids=(
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
    extraction_texts=(
        # Two DOE Office of Science grants in prose — both confirmed via USASpending.
        ExtractionExample(
            text="Support from DE-SC0021358 and DE-SC0016260 enabled this research.",
            expected_extracted=("DE-SC0021358", "DE-SC0016260"),
            verified_existing=("DE-SC0021358", "DE-SC0016260"),
        ),
        # DOE + NSF mixed text — NSF 1728743 lacks a DE- prefix so only DOE IDs extracted.
        ExtractionExample(
            text="Research funded by DE-SC0021358, NSF 1728743, and DE-OE0000895.",
            expected_extracted=("DE-SC0021358", "DE-OE0000895"),
            verified_existing=("DE-SC0021358", "DE-OE0000895"),
        ),
    ),
)
