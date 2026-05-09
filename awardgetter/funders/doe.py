"""Funder matcher for the U.S. Department of Energy (DOE)."""

import re
from pathlib import Path

import requests

from .._award import AwardDetailsResult, AwardNotFound, NotFoundReason
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes
from ._usaspending import query_usaspending

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

# Strips leading "Contract [No.] " or "No. " before an award number.
_NO_PREFIX_RE = re.compile(r"^\s*(?:[Cc]ontract\s+)?[Nn]o\.?\s+")
_CONTRACT_PREFIX_RE = re.compile(r"^\s*[Cc]ontract\s+")

# Bare SC\d+ IDs missing the "DE-" prefix (e.g. SC0010008 → DE-SC0010008).
_DOE_SC_BARE_RE = re.compile(r"(?<![A-Z\-])SC(\d{7,10})\b", re.IGNORECASE)

# Bare AC\d{2}-... IDs where "DE-" prefix was cut off (e.g. AC05-06OR23177 → DE-AC05-06OR23177).
# Negative lookbehind prevents matching when already preceded by "DE-" or another letter.
_DOE_AC_BARE_RE = re.compile(r"(?<![A-Z\d])AC(\d{2}[-])", re.IGNORECASE)
# Leading hyphen before AC (e.g. "-AC02-05CH11231").
_DOE_LEADING_HYPHEN_RE = re.compile(r"^-AC\d{2}-", re.IGNORECASE)
# Collapse errant space within a DE-format component: "DE-AC02- 06CH11357" → "DE-AC02-06CH11357"
_DOE_INTERNAL_SPACE_RE = re.compile(r"\b(DE-?[A-Z]{2}-?) (\d)", re.IGNORECASE)

# Management & Operating contracts: DE-AC{NN}-{YY}{XX}{NNNNN}
# These are lab-wide umbrella contracts, not individual research grants.
_DOE_MO_RE = re.compile(r"^DE-AC\d{2}-\d{2}[A-Z]{2}\d+$")

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


def _normalize_doe(text: str) -> str:
    s = normalize_dashes(text)
    s = _CONTRACT_PREFIX_RE.sub("", s)
    s = _NO_PREFIX_RE.sub("", s)
    s = _DOE_PREFIX_RE.sub("DE-", s)
    # Strip a leading "-" before bare AC\d{2}- (e.g. "-AC02-05CH11231" → "AC02-05CH11231").
    if _DOE_LEADING_HYPHEN_RE.match(s):
        s = s[1:]
    # Prepend "DE-" to bare AC\d{2}- patterns missing the prefix.
    s = _DOE_AC_BARE_RE.sub(r"DE-AC\1", s)
    # Collapse errant space within DE-format components (e.g. "DE-AC02- 06CH11357").
    s = _DOE_INTERNAL_SPACE_RE.sub(r"\1\2", s)
    return s


def check_award_id(text: str) -> bool:
    s = _normalize_doe(text)
    return bool(_DOE_RE.search(s) or _DOE_SC_BARE_RE.search(s))


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
    # Bare SC\d+ with missing DE- prefix (e.g. "SC0010008" → "DE-SC0010008").
    for m in _DOE_SC_BARE_RE.finditer(s):
        val = "DE-SC" + m.group(1).upper()
        if val not in seen:
            seen.add(val)
            results.append(val)
    return results


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    # Pre-filter M&O contracts — they match the regex but are not individual grants.
    to_query: list[str] = []
    pre_not_found: list[AwardNotFound] = []
    for award_id in award_ids:
        if _DOE_MO_RE.match(award_id):
            pre_not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="M&O contract (lab-wide umbrella contract, not an individual grant)",
                )
            )
        else:
            to_query.append(award_id)

    result = query_usaspending(to_query, FUNDER_ID)

    # For pre-2007 grants not found in USASpending, check OSTI and adjust detail.
    updated_not_found: list[AwardNotFound] = list(pre_not_found)
    for nf in result.not_found:
        if nf.reason == NotFoundReason.NOT_FOUND and _DOE_PRE2007_RE.match(nf.input_text):
            if _osti_confirms_pre2007(nf.input_text):
                updated_not_found.append(
                    AwardNotFound(
                        funder_id=FUNDER_ID,
                        input_text=nf.input_text,
                        reason=NotFoundReason.NOT_FOUND,
                        detail="Pre-2007 grant confirmed in OSTI"
                        " (financial data not available via public APIs)",
                    )
                )
            else:
                updated_not_found.append(
                    AwardNotFound(
                        funder_id=FUNDER_ID,
                        input_text=nf.input_text,
                        reason=NotFoundReason.NOT_FOUND,
                        detail="Not found in USASpending or OSTI",
                    )
                )
        else:
            updated_not_found.append(nf)

    return AwardDetailsResult(found=result.found, not_found=updated_not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
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
        # Bare SC\d+ missing the DE- prefix — normalised to DE-SC... before lookup.
        "SC0021358",
        "SC0022917",
        # "Contract [No.]" prefix stripped before matching.
        "Contract DE-SC0021358",
        "Contract No. DE-SC0021358",
        # Bare AC\d{2}- with missing DE- prefix — normalised to DE-AC... before matching.
        "AC05-06OR23177",
        "-AC02-05CH11231",
        # Errant space within DE-format components — collapsed before matching.
        "DE-AC02- 06CH11357",
        "DE-SC- 0018660",
    ),
    not_found_awards=(
        # Bare SC ID that normalises but grant does not exist in USASpending.
        "SC0000001",
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
        # Bare AC\d{2}- with missing DE- — normalised to DE-AC... → M&O contract → NOT_FOUND.
        "AC05-06OR23177",
        "-AC02-05CH11231",
        "AC02-05-CH11231",
    ),
    rejected_ids=(
        # BER programme tracking codes — not award numbers.
        "ERKJ335",
        # Numeric-only / label-only inputs.
        "62201",
        "COVID-19",
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
