"""Funder matcher for UKRI research councils (EPSRC, MRC, BBSRC, NERC, ESRC, AHRC, STFC)."""

import re
import time
from datetime import date, datetime
from pathlib import Path

import requests

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._spec import FunderExamples
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

_UKRI_RE = re.compile(r"\b(?:EP|MR|BB|NE|ES|AH|ST|GR)/[A-Z0-9]{6,9}(?:/\d+)?\b")

_GTR_API_URL = "https://gtr.ukri.org/api/projects?ref={ref}"
_GTR_RATE_LIMIT_SLEEP = 1.0


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
    s = normalize_dashes(text)
    return bool(_UKRI_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    return _UKRI_RE.findall(normalize_dashes(text))


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
            resp = requests.get(
                _GTR_API_URL.format(ref=award_id),
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
            continue

        if resp.status_code == 404:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="Grant reference not found in GtR",
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

        data = resp.json()
        try:
            project = data["projectComposition"]["project"]
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
    positive=(
        # Standard EPSRC references with `/N` suffix.
        "EP/S00923X/1",
        "EP/I013067/1",
        "EP/P020259/1",
        "EP/S022961/1",
        "EP/V002856/1",
        "EP/M025179/1",
        # Incomplete — missing trailing `/N`.
        "EP/L01663X",
        "EP/L016508",
        # Trailing-slash and trailing-paren tolerated by the word-boundary regex.
        "EP/R513295/",
        "EP/P020259/1)",
        # Embedded in surrounding text or multi-grant strings.
        "MVSE EP/V002856/1",
        "EP/I013067/1 and EP/M025179/1",
    ),
    negative=(
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
)
