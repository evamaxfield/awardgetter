"""Funder matcher for the U.S. National Institutes of Health (NIH)."""

import re
from datetime import datetime
from pathlib import Path

import requests

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._spec import FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "nih"
FUNDER_DISPLAY_NAME: str = "U.S. National Institutes of Health"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = (
    "nci",
    "nigms",
    "niaid",
    "nimh",
    "nhlbi",
    "niddk",
    "ninds",
    "nichd",
    "nibib",
    "nia",
    "niehs",
    "nidcd",
    "nidcr",
    "nida",
    "niams",
    "nei",
    "ninr",
    "nlm",
    "fic",
    "nccih",
    "ncats",
)
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = (
    "National Cancer Institute",
    "National Institute of General Medical Sciences",
    "National Institute of Allergy and Infectious Diseases",
    "National Institute of Mental Health",
    "National Heart, Lung, and Blood Institute",
    "National Institute of Diabetes and Digestive and Kidney Diseases",
    "National Institute of Neurological Disorders and Stroke",
    "Eunice Kennedy Shriver National Institute of Child Health and Human Development",
    "National Institute of Biomedical Imaging and Bioengineering",
    "National Institute on Aging",
    "National Institute of Environmental Health Sciences",
    "National Institute on Deafness and Other Communication Disorders",
    "National Institute of Dental and Craniofacial Research",
    "National Institute on Drug Abuse",
    "National Institute of Arthritis and Musculoskeletal and Skin Diseases",
    "National Eye Institute",
    "National Institute of Nursing Research",
    "National Library of Medicine",
    "National Center for Complementary and Integrative Health",
    "National Center for Advancing Translational Sciences",
)

_NIH_AGENCY_WORDS_RE = re.compile(
    r"\b(?:NIH|DHHS|HHS|NCI|NIGMS|NIAID|NIMH|NHLBI|NIDDK|NINDS|NICHD|NIBIB"
    r"|NIA|NIEHS|NIDCD|NIDCR|NIDA|NIAMS|NEI|NINR|NLM|FIC|NCCIH|NCATS)\b",
    re.IGNORECASE,
)

_NIH_BRACKETED_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)")

_NIH_SUPPL_RE = re.compile(r"(?i)\bSuppl\w*\b")

# Canonical NIH project-number pattern: optional application-type digit,
# 3-char activity code (R01, T32, RF1, DP1, UG3, ...), 2-char institute
# code, 4-6 digit serial, optional support-year suffix. Match against a
# normalized string so multi-id cells return True on any one hit.
_NIH_CORE_PATTERN = re.compile(
    r"[1-9]?"
    r"(?:[A-Z]\d{2}|[A-Z]{2}\d)"
    r"[-\s]*"
    r"[A-Z]{2}"
    r"[-\s]*"
    r"\d{4,6}"
    r"(?:\d{2}(?:[A-Z]\d)?)?"
    r"(?:-\d{1,2}(?:[A-Z]\d{0,2})?)?",
    re.IGNORECASE,
)

_NIH_REPORTER_URL = "https://api.reporter.nih.gov/v2/projects/search"
_NIH_BATCH_SIZE = 50

_STRIP_APP_TYPE_RE = re.compile(r"^\d")
_STRIP_SUPPORT_YEAR_RE = re.compile(r"-\d+.*$")


def _parse_nih_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def _fetch_nih_batch(
    batch: list[str],
) -> tuple[list[dict], list[AwardNotFound]]:
    results: list[dict] = []
    errors: list[AwardNotFound] = []
    try:
        resp = requests.post(
            _NIH_REPORTER_URL,
            json={"criteria": {"project_nums": batch}, "limit": _NIH_BATCH_SIZE},
            timeout=30,
        )
    except requests.exceptions.RequestException as exc:
        errors.extend(
            AwardNotFound(
                funder_id=FUNDER_ID,
                input_text=aid,
                reason=NotFoundReason.API_ERROR,
                detail=str(exc),
            )
            for aid in batch
        )
        return results, errors

    if resp.status_code == 429:
        errors.extend(
            AwardNotFound(
                funder_id=FUNDER_ID,
                input_text=aid,
                reason=NotFoundReason.RATE_LIMITED,
                detail="HTTP 429",
            )
            for aid in batch
        )
        return results, errors

    if not resp.ok:
        errors.extend(
            AwardNotFound(
                funder_id=FUNDER_ID,
                input_text=aid,
                reason=NotFoundReason.API_ERROR,
                detail=f"HTTP {resp.status_code}",
            )
            for aid in batch
        )
        return results, errors

    results.extend(resp.json().get("results", []))
    return results, errors


def _normalize(text: str) -> str:
    s = normalize_dashes(text)
    s = _NIH_BRACKETED_RE.sub(" ", s)
    s = _NIH_AGENCY_WORDS_RE.sub(" ", s)
    return _NIH_SUPPL_RE.sub(" ", s)


def _base_project_num(num: str) -> str:
    """Return the core project number stripped of application-type digit and support year."""
    s = _STRIP_APP_TYPE_RE.sub("", num.upper().strip())
    return _STRIP_SUPPORT_YEAR_RE.sub("", s)


def check_award_id(text: str) -> bool:
    return bool(_NIH_CORE_PATTERN.search(_normalize(text)))


def extract_award_ids(text: str) -> list[str]:
    matches = _NIH_CORE_PATTERN.findall(_normalize(text))
    return [re.sub(r"[-\s]+", "", _base_project_num(m)) for m in matches]


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    all_results: list[dict] = []
    for i in range(0, len(award_ids), _NIH_BATCH_SIZE):
        batch_results, batch_errors = _fetch_nih_batch(award_ids[i : i + _NIH_BATCH_SIZE])
        all_results.extend(batch_results)
        not_found.extend(batch_errors)

    groups: dict[str, list[dict]] = {}
    for row in all_results:
        base = _base_project_num(row.get("project_num", ""))
        groups.setdefault(base, []).append(row)

    for award_id in award_ids:
        base = _base_project_num(award_id)
        rows = groups.get(base)
        if not rows:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="No matching project in NIH RePORTER",
                )
            )
            continue

        amounts = [r["award_amount"] for r in rows if r.get("award_amount")]
        starts = [
            _parse_nih_date(r.get("project_start_date"))
            for r in rows
            if r.get("project_start_date")
        ]
        ends = [
            _parse_nih_date(r.get("project_end_date"))
            for r in rows
            if r.get("project_end_date")
        ]
        starts_clean = [d for d in starts if d is not None]
        ends_clean = [d for d in ends if d is not None]

        found.append(
            AwardDetails(
                funder_id=FUNDER_ID,
                award_id=base,
                amount_funded=sum(amounts) if amounts else None,
                currency="USD",
                start_date=min(starts_clean) if starts_clean else None,
                end_date=max(ends_clean) if ends_clean else None,
            )
        )

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="awardgetter/funders/nih.py (no plan file)",
    verified_awards=(
        # Canonical project numbers confirmed via NIH RePORTER.
        "U24NS124001",
        "U24CA086368",
        "T32GM007347",
        # With application-type digit and support-year suffix.
        "5U24NS124001-05",
        "5U24CA086368-25",
    ),
    matching_ids=(
        # NIH agency word and bracketed text are stripped before matching.
        "[NIH] U24NS124001",
        "NIH U24NS124001",
        # Internal whitespace within the project number is tolerated.
        "U24 NS 124001",
    ),
    not_found_awards=(),
    rejected_ids=(
        "EP/S00923X/1",
        "ANR-21-CE29-0003",
        "2022ZD0160401",
        "DFG SFB1114",
        "12345",
    ),
    extraction_texts=(),
)
