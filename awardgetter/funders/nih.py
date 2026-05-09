"""Funder matcher for the U.S. National Institutes of Health (NIH)."""

import re
from datetime import datetime
from pathlib import Path

import requests

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._spec import ExtractionExample, FunderExamples
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
FUNDER_OPENALEX_ID: str = "F4320332161"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ("F4320337351",)  # NCI

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
_STRIP_SUPPORT_YEAR_RE = re.compile(r"-\d{1,2}(?:[A-Z]\d*)?$")
_FIX_ACTIVITY_O_RE = re.compile(r"^([A-Z])O(\d[A-Z]{2})")
_ZERO_PAD_SERIAL_RE = re.compile(r"([A-Z]{2})(\d+)$")
_NIH_BARE_SERIAL_RE = re.compile(r"\b[A-Z]{2}\d{5,6}\b")
# Detects a bare institute+serial after extraction (no activity code prefix).
_IS_BARE_SERIAL_RE = re.compile(r"^[A-Z]{2}\d{5,6}$")


def _parse_nih_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def _fetch_nih_wildcard(bare_serial: str) -> tuple[list[dict], AwardNotFound | None]:
    """Query NIH RePORTER with a wildcard for a bare institute+serial (e.g. GM061300).

    Returns all matching project rows and any error, or an AwardNotFound on failure.
    The wildcard ``%GM061300`` matches any project number ending in that serial regardless
    of activity code (R01, K01, P30, etc.).
    """
    try:
        resp = requests.post(
            _NIH_REPORTER_URL,
            json={"criteria": {"project_nums": [f"%{bare_serial}"]}, "limit": _NIH_BATCH_SIZE},
            timeout=30,
        )
    except requests.exceptions.RequestException as exc:
        return [], AwardNotFound(
            funder_id=FUNDER_ID,
            input_text=bare_serial,
            reason=NotFoundReason.API_ERROR,
            detail=str(exc),
        )

    if resp.status_code == 429:
        return [], AwardNotFound(
            funder_id=FUNDER_ID,
            input_text=bare_serial,
            reason=NotFoundReason.RATE_LIMITED,
            detail="HTTP 429",
        )
    if not resp.ok:
        return [], AwardNotFound(
            funder_id=FUNDER_ID,
            input_text=bare_serial,
            reason=NotFoundReason.API_ERROR,
            detail=f"HTTP {resp.status_code}",
        )
    return resp.json().get("results", []), None


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


def _normalize_no_brackets(text: str) -> str:
    s = normalize_dashes(text)
    s = _NIH_AGENCY_WORDS_RE.sub(" ", s)
    return _NIH_SUPPL_RE.sub(" ", s)


def _base_project_num(num: str) -> str:
    """Return the core project number stripped of application-type digit and support year."""
    s = _STRIP_APP_TYPE_RE.sub("", num.upper().strip())
    return _STRIP_SUPPORT_YEAR_RE.sub("", s)


def _normalize_activity_code(s: str) -> str:
    """Replace O→0 typos in the activity-code digit position (e.g. RO1 → R01)."""
    return _FIX_ACTIVITY_O_RE.sub(lambda m: m.group(1) + "0" + m.group(2), s)


def _zero_pad_serial(s: str) -> str:
    """Zero-pad the terminal serial number to 6 digits when shorter.

    E.g. R01GM60595 → R01GM060595.
    """
    m = _ZERO_PAD_SERIAL_RE.search(s)
    if m and len(m.group(2)) < 6:
        return s[: m.start()] + m.group(1) + m.group(2).zfill(6)
    return s


def check_award_id(text: str) -> bool:
    for norm in (_normalize_no_brackets(text), _normalize(text)):
        if _NIH_CORE_PATTERN.search(norm) or _NIH_BARE_SERIAL_RE.search(norm):
            return True
    return False


def extract_award_ids(text: str) -> list[str]:
    # Try without bracket stripping first so IDs inside brackets aren't lost.
    for norm in (_normalize_no_brackets(text), _normalize(text)):
        matches = _NIH_CORE_PATTERN.findall(norm)
        if matches:
            return [
                _zero_pad_serial(
                    _normalize_activity_code(re.sub(r"[-\s]+", "", _base_project_num(m)))
                )
                for m in matches
            ]
    normalized = _normalize(text)
    # Fallback: bare institute+serial without activity code — will likely be NOT_FOUND
    # but converts PARSE_ERROR → NOT_FOUND for better observability.
    return _NIH_BARE_SERIAL_RE.findall(normalized)


def _aggregate_rows(award_id: str, rows: list[dict]) -> AwardDetails:
    amounts = [r["award_amount"] for r in rows if r.get("award_amount") is not None]
    starts = [
        _parse_nih_date(r.get("project_start_date"))
        for r in rows
        if r.get("project_start_date")
    ]
    ends = [
        _parse_nih_date(r.get("project_end_date")) for r in rows if r.get("project_end_date")
    ]
    starts_clean = [d for d in starts if d is not None]
    ends_clean = [d for d in ends if d is not None]
    return AwardDetails(
        funder_id=FUNDER_ID,
        award_id=award_id,
        amount_funded=sum(amounts) if amounts else None,
        currency="USD",
        start_date=min(starts_clean) if starts_clean else None,
        end_date=max(ends_clean) if ends_clean else None,
    )


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    # Partition: bare institute+serial IDs (no activity code) use a wildcard query;
    # full project numbers use the standard batch lookup.
    bare_serials = [aid for aid in award_ids if _IS_BARE_SERIAL_RE.match(aid)]
    normal_ids = [aid for aid in award_ids if not _IS_BARE_SERIAL_RE.match(aid)]

    # Standard batch lookup for full project numbers.
    all_results: list[dict] = []
    for i in range(0, len(normal_ids), _NIH_BATCH_SIZE):
        batch_results, batch_errors = _fetch_nih_batch(normal_ids[i : i + _NIH_BATCH_SIZE])
        all_results.extend(batch_results)
        not_found.extend(batch_errors)

    groups: dict[str, list[dict]] = {}
    for row in all_results:
        base = _base_project_num(row.get("project_num", ""))
        groups.setdefault(base, []).append(row)

    for award_id in normal_ids:
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
        found.append(_aggregate_rows(base, rows))

    # Wildcard lookup for bare institute+serial IDs (e.g. GM061300 → %GM061300).
    for bare_serial in bare_serials:
        rows, error = _fetch_nih_wildcard(bare_serial)
        if error is not None:
            not_found.append(error)
            continue
        if not rows:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=bare_serial,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="No matching project in NIH RePORTER (wildcard search)",
                )
            )
            continue
        # Group wildcard results by base project number and emit one AwardDetails per group.
        wc_groups: dict[str, list[dict]] = {}
        for row in rows:
            base = _base_project_num(row.get("project_num", ""))
            wc_groups.setdefault(base, []).append(row)
        for base, base_rows in wc_groups.items():
            found.append(_aggregate_rows(base, base_rows))

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
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
        # Bare institute+serial without activity code — matched by fallback pattern.
        "GM061300",
        "NS095892",
        # NIH agency word and bracketed text are stripped before matching.
        "[NIH] U24NS124001",
        "NIH U24NS124001",
        # Internal whitespace within the project number is tolerated.
        "U24 NS 124001",
        # Separator-heavy format — support-year suffix stripped correctly.
        "2-R01-DC-009209-11",
        # Common O→0 typo in activity code.
        "RO1-MH-075916",
        # Short (5-digit) serial — zero-padded to 6.
        "R01 GM60595",
        # Grant ID inside parentheses — two-pass bracket handling extracts it.
        "(P30 CA015704)",
        # Revision/supplement suffixes (-01A1, -02S1) stripped by updated regex.
        "1R01CA248422-01A1",
        "3R01HL-117626-02S1",
        # Bracket with app-type digit and revision suffix.
        "[2R01HG007182-04A1]",
    ),
    not_found_awards=(
        # Fake institute codes (ZZ, XX, YY) — format-valid but nonexistent in NIH RePORTER.
        "R01ZZ999999",
        "U24XX000001",
        "T32YY111111",
        # Bare institute+serial that doesn't exist under any activity code.
        "ZZ999999",
    ),
    rejected_ids=(
        "EP/S00923X/1",
        "ANR-21-CE29-0003",
        "2022ZD0160401",
        "DFG SFB1114",
        "12345",
    ),
    extraction_texts=(
        # Two NIH project numbers in prose — both confirmed via NIH RePORTER.
        ExtractionExample(
            text="We acknowledge NIH support under grants U24NS124001 and T32GM007347.",
            expected_extracted=("U24NS124001", "T32GM007347"),
            verified_existing=("U24NS124001", "T32GM007347"),
        ),
        # Application-type digit and support-year suffix stripped by _base_project_num.
        ExtractionExample(
            text="NIH grants 5U24NS124001-05 and 5U24CA086368-25 funded this work.",
            expected_extracted=("U24NS124001", "U24CA086368"),
            verified_existing=("U24NS124001", "U24CA086368"),
        ),
        # Revision suffix (-01A1) stripped correctly.
        ExtractionExample(
            text="1R01CA248422-01A1",
            expected_extracted=("R01CA248422",),
            verified_existing=(),
        ),
    ),
)
