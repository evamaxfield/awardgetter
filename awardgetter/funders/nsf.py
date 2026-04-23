"""Funder matcher for the U.S. National Science Foundation (NSF)."""

import re
from datetime import datetime
from pathlib import Path

import requests

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "nsf"
FUNDER_DISPLAY_NAME: str = "U.S. National Science Foundation"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ()
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ("National Science Foundation",)
FUNDER_OPENALEX_ID: str = "F4320306076"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ()

_NSF_WORD_RE = re.compile(r"\bNSF\b", re.IGNORECASE)
_NSF_LETTER_PREFIX_RE = re.compile(r"\b[A-Z]{2,4}(?=\d)")
_DIGIT_SEPARATOR_DIGIT_RE = re.compile(r"(\d)[\s\-]+(\d)")
_NSF_AWARD_ID_RE = re.compile(r"\b\d{5,7}\b")

_NSF_API_URL = (
    "https://api.nsf.gov/services/v1/awards.json"
    "?id={award_id}&printFields=id,fundsObligatedAmt,startDate,expDate"
)


def _normalize(text: str) -> str:
    s = normalize_dashes(text)
    s = _NSF_WORD_RE.sub(" ", s)
    s = _NSF_LETTER_PREFIX_RE.sub("", s)
    return _DIGIT_SEPARATOR_DIGIT_RE.sub(r"\1\2", s)


def check_award_id(text: str) -> bool:
    return bool(_NSF_AWARD_ID_RE.search(_normalize(text)))


def extract_award_ids(text: str) -> list[str]:
    return _NSF_AWARD_ID_RE.findall(_normalize(text))


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    for award_id in award_ids:
        padded_id = award_id.zfill(7)
        try:
            resp = requests.get(
                _NSF_API_URL.format(award_id=padded_id),
                timeout=15,
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

        awards = resp.json().get("response", {}).get("award", [])
        if not awards:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="No award returned by NSF API",
                )
            )
            continue

        award = awards[0]
        amount_raw = award.get("fundsObligatedAmt")
        amount = float(amount_raw) if amount_raw else None

        def _parse_nsf_date(s: str | None):
            if not s:
                return None
            try:
                return datetime.strptime(s, "%m/%d/%Y").date()
            except ValueError:
                return None

        found.append(
            AwardDetails(
                funder_id=FUNDER_ID,
                award_id=award.get("id", award_id),
                amount_funded=amount,
                currency="USD",
                start_date=_parse_nsf_date(award.get("startDate")),
                end_date=_parse_nsf_date(award.get("expDate")),
            )
        )

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="awardgetter/funders/nsf.py (no plan file)",
    verified_awards=(
        # Bare 7-digit NSF award IDs confirmed via NSF API.
        "1728743",
        "2211275",
    ),
    matching_ids=(
        # NSF agency word is stripped, then 5-7 digit match.
        "NSF-2211275",
        "NSF 1728743",
        # Generic surrounding text.
        "Award #2211275",
        # Internal whitespace within the 7 digits is collapsed.
        "NSF 22 11275",
        # Division/program prefix without hyphen — prefix is stripped generically.
        "DEB1657662",
        "OCE1238212",
        "MCB2046798",
        # Shorter IDs from papers that omit leading zeros — zero-padded for API lookup.
        "131060",
    ),
    not_found_awards=(
        # 7-digit format-valid IDs that are clearly fabricated.
        "1234567",
        "9999999",
        "0000001",
    ),
    rejected_ids=(
        # Wrong digit counts — 8-digit numbers not matched by check_award_id.
        "62206216",
        # Cross-funder distractors where prefix stripping leaves no 7-digit run.
        "EP/S00923X/1",
        "ANR-21-CE29-0003",
        "2022ZD0160401",
    ),
    extraction_texts=(
        # Two NSF IDs embedded in prose — both verified via NSF API.
        ExtractionExample(
            text="This work was supported by NSF grants 1728743 and 2211275.",
            expected_extracted=("1728743", "2211275"),
            verified_existing=("1728743", "2211275"),
        ),
        # NSF ID alongside an ANR ID — ANR token has no 7-digit runs so only
        # the NSF number is returned by the NSF extractor.
        ExtractionExample(
            text="Funding from NSF 1728743 and ANR-21-CE29-0003 enabled this research.",
            expected_extracted=("1728743",),
            verified_existing=("1728743",),
        ),
    ),
)
