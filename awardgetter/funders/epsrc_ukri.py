"""Funder matcher for UKRI research councils (EPSRC, MRC, BBSRC, NERC, ESRC, AHRC, STFC)."""

import re
import time
from datetime import date, datetime
from pathlib import Path

import requests

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "epsrc_ukri"
FUNDER_DISPLAY_NAME: str = "UK Research and Innovation (UKRI) councils"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = (
    "epsrc",
    "mrc",
    "bbsrc",
    "nerc",
    "esrc",
    "ahrc",
    "stfc",
    "ukri",
)
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = (
    "Engineering and Physical Sciences Research Council",
    "Medical Research Council",
    "UK Research and Innovation",
    "Biotechnology and Biological Sciences Research Council",
    "Natural Environment Research Council",
    "Economic and Social Research Council",
    "Arts and Humanities Research Council",
    "Science and Technology Facilities Council",
)
FUNDER_OPENALEX_ID: str = "F4320334627"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ()

_UKRI_RE = re.compile(r"\b[A-Z]{2}/[A-Z0-9]{6,9}(?:/\d+)?\b")
_UKRI_NUMERIC_RE = re.compile(r"\b\d{7}\b")
# Catches grant refs where the '/' separator was omitted (e.g. EPN036106/1 → EP/N036106/1).
_UKRI_MISSING_SLASH_RE = re.compile(r"\b([A-Z]{2})([A-Z][A-Z0-9]{5,8}/\d+)\b")

_GTR_API_URL = "https://gtr.ukri.org/api/projects?ref={ref}"
_GTR_RATE_LIMIT_SLEEP = 1.0


def _normalize_epsrc(text: str) -> str:
    s = normalize_dashes(text)
    # Collapse errant space after two-letter council prefix and slash:
    # "EP/ L016796/1" → "EP/L016796/1"
    s = re.sub(r"\b([A-Z]{2})/ +", r"\1/", s)
    return _UKRI_MISSING_SLASH_RE.sub(r"\1/\2", s)


def _parse_gtr_date(value: str | int | None) -> date | None:
    if value is None:
        return None
    # Try ISO string first (e.g. "2019-01-01" or "2019-01-01T00:00:00").
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            pass
        # Try Unix-ms integer embedded in a string.
        try:
            return datetime.fromtimestamp(int(value) / 1000).date()
        except (ValueError, OSError):
            return None
    # Unix-ms integer.
    if isinstance(value, int):
        try:
            return datetime.fromtimestamp(value / 1000).date()
        except OSError:
            return None
    return None


def check_award_id(text: str) -> bool:
    s = _normalize_epsrc(text)
    return bool(_UKRI_RE.search(s) or _UKRI_NUMERIC_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    s = _normalize_epsrc(text)
    seen: set[str] = set()
    result: list[str] = []
    for val in _UKRI_RE.findall(s) + _UKRI_NUMERIC_RE.findall(s):
        if val not in seen:
            seen.add(val)
            result.append(val)
    return result


def _request_with_404_retry(award_id: str) -> tuple[requests.Response, str]:
    """Make a GtR API request, retrying with /1 suffix on 404 if needed.

    Returns (response, effective_award_id). Raises RequestException on network error.
    """
    resp = requests.get(
        _GTR_API_URL.format(ref=award_id),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    # Retry with /1 suffix if the reference has no trailing serial number.
    # Many truncated references (e.g. EP/F067496) are simply missing the /1.
    if resp.status_code == 404 and not re.search(r"/\d+$", award_id):
        retried_id = award_id + "/1"
        try:
            retried = requests.get(
                _GTR_API_URL.format(ref=retried_id),
                headers={"Accept": "application/json"},
                timeout=30,
            )
            if retried.ok:
                return retried, retried_id
        except requests.exceptions.RequestException:
            pass
    return resp, award_id


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    for i, award_id in enumerate(award_ids):
        if i > 0:
            time.sleep(_GTR_RATE_LIMIT_SLEEP)

        try:
            resp, award_id = _request_with_404_retry(award_id)
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
            is_404 = resp.status_code == 404
            reason = NotFoundReason.NOT_FOUND if is_404 else NotFoundReason.API_ERROR
            detail = (
                "Grant reference not found in GtR" if is_404 else f"HTTP {resp.status_code}"
            )
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=reason,
                    detail=detail,
                )
            )
            continue

        data = resp.json()
        try:
            project = data["projectOverview"]["projectComposition"]["project"]
            fund = project["fund"]
            amount_raw = fund.get("valuePounds")
            amount = float(amount_raw) if amount_raw is not None else None
            start_date = _parse_gtr_date(fund.get("start"))
            end_date = _parse_gtr_date(fund.get("end"))
        except (KeyError, TypeError, ValueError):
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.API_ERROR,
                    detail="Unexpected GtR response structure",
                )
            )
            continue

        found.append(
            AwardDetails(
                funder_id=FUNDER_ID,
                award_id=award_id,
                amount_funded=amount,
                currency="GBP",
                start_date=start_date,
                end_date=end_date,
            )
        )

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/epsrc_gtr_spec.md",
    verified_awards=(
        # Standard EPSRC/UKRI references confirmed via GtR API.
        "EP/I013067/1",
        "EP/P020259/1",
        "EP/D05592X/1",
        "EP/V002856/1",
        "EP/M025179/1",
        # MRC reference — also matched by the UKRI council-prefix pattern.
        "MR/R001154/1",
    ),
    matching_ids=(
        # Pure numeric GtR project ID (overlaps with NSF by design).
        "2882321",
        # Trailing-paren tolerated by the word-boundary regex.
        "EP/P020259/1)",
        # Embedded in surrounding text.
        "MVSE EP/V002856/1",
        # References missing the trailing /1 — retried automatically on 404.
        "EP/F067496",
        "EP/N007638",
        # Missing '/' separator between council prefix and grant body — normalised.
        "EPN036106/1",
        # Errant space after council prefix slash — collapsed before matching.
        "EP/ L016796/1",
        "MR/ T018429/1",
    ),
    not_found_awards=(
        # Z-prefix references do not exist in the GtR database.
        "EP/Z999999/1",
        "MR/Z999999/1",
        "BB/Z999999/1",
    ),
    rejected_ids=(
        # Wellcome Trust — not part of UKRI.
        "WT101957",
        "WT203148/Z/16/Z",
        # Older format references not in the council-prefix alternation.
        "M009521/1",
        "P008739/1",
        "F500385/1",
        "K000128",
        # Free-text labels and external funder names.
        "CoMPLEX PhD studentship",
        "PhD Scholarship",
        "Mathematics",
        "Programme grant",
        "Not applicable",
        "NVIDIA",
        # Cross-funder distractors.
        "ANR-21-CE29-0003",
        "DE-SC0021358",
        "62206216",
    ),
    extraction_texts=(
        # Two UKRI grants in one string — both verified in GtR.
        ExtractionExample(
            text="EP/I013067/1 and EP/M025179/1",
            expected_extracted=("EP/I013067/1", "EP/M025179/1"),
            verified_existing=("EP/I013067/1", "EP/M025179/1"),
        ),
        # Three UKRI grants across two councils embedded in prose — all verified.
        ExtractionExample(
            text=(
                "Research was supported by EPSRC grants EP/P020259/1, "
                "MR/R001154/1, and EP/V002856/1."
            ),
            expected_extracted=("EP/P020259/1", "MR/R001154/1", "EP/V002856/1"),
            verified_existing=("EP/P020259/1", "MR/R001154/1", "EP/V002856/1"),
        ),
        # EPSRC + ANR mixed text — ANR token contains no bare 7-digit numbers so
        # _UKRI_NUMERIC_RE does not over-extract.
        ExtractionExample(
            text=(
                "Funded by EPSRC EP/D05592X/1 and ANR-21-CE29-0003, "
                "with support from EP/I013067/1."
            ),
            expected_extracted=("EP/D05592X/1", "EP/I013067/1"),
            verified_existing=("EP/D05592X/1", "EP/I013067/1"),
        ),
    ),
)
