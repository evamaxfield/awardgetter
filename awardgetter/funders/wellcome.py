"""Funder matcher for the Wellcome Trust."""

import re
from datetime import date
from pathlib import Path

import polars as pl

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._cache import get_cached_file
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "wellcome"
FUNDER_DISPLAY_NAME: str = "Wellcome Trust"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ("wellcome_trust",)
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ("Wellcome",)
FUNDER_OPENALEX_ID: str = "F4320311904"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ("F4320307874",)  # "Wellcome"

_WELLCOME_XLSX_URL = (
    "https://cms.wellcome.org/sites/default/files"
    "/2026-02/Wellcome-grants-awarded-1-October-2000-to-27-January-2026.xlsx"
)
_WELLCOME_XLSX_FILENAME = "wellcome_grants.xlsx"

# Full slash format: 104169/Z/14/A  — 5-6 digits / letter / 2 digits / optional letter
_WELLCOME_FULL_RE = re.compile(r"\b\d{5,6}/[A-Z]/\d{2}/[A-Z]?\b", re.IGNORECASE)
# WT-prefixed: WT096185
_WELLCOME_WT_RE = re.compile(r"\bWT(\d{5,6})\b", re.IGNORECASE)

# Strip WT prefix and leading # before normalisation.
_WT_PREFIX_RE = re.compile(r"^WT", re.IGNORECASE)
_HASH_PREFIX_RE = re.compile(r"^#")

# Numeric prefix: digits before the first slash (used for prefix-only lookups).
_NUMERIC_PREFIX_RE = re.compile(r"^(\d{5,6})")


def _normalize_wellcome(text: str) -> str:
    s = normalize_dashes(text).strip()
    s = _HASH_PREFIX_RE.sub("", s)
    s = _WT_PREFIX_RE.sub("", s)
    return s.upper()


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_WELLCOME_FULL_RE.search(s) or _WELLCOME_WT_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    s = normalize_dashes(text)
    seen: set[str] = set()
    results: list[str] = []
    for pattern in (_WELLCOME_FULL_RE, _WELLCOME_WT_RE):
        for m in pattern.finditer(s):
            val = m.group(0).upper()
            if val not in seen:
                seen.add(val)
                results.append(val)
    return results


def _load_lookup(
    cache_dir: Path,
    force_refresh: bool,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Return (full_lookup, prefix_lookup) from the cached Wellcome XLSX.

    full_lookup:   Internal ID (uppercase) → row dict
    prefix_lookup: leading digits → highest-amount row dict (for bare-number lookups)
    """
    xlsx_path = get_cached_file(
        _WELLCOME_XLSX_URL,
        _WELLCOME_XLSX_FILENAME,
        cache_dir,
        force_refresh,
    )
    df = pl.read_excel(xlsx_path).select(
        [
            "Internal ID",
            "Amount Awarded",
            "Currency",
            "Planned Dates:Start Date",
            "Planned Dates:End Date",
        ]
    )

    full_lookup: dict[str, dict] = {}
    prefix_lookup: dict[str, dict] = {}

    for row in df.to_dicts():
        internal_id = (row.get("Internal ID") or "").strip().upper()
        if not internal_id:
            continue
        full_lookup[internal_id] = row
        m = _NUMERIC_PREFIX_RE.match(internal_id)
        if m:
            prefix = m.group(1)
            existing = prefix_lookup.get(prefix)
            amt = row.get("Amount Awarded") or 0
            existing_amt = (existing or {}).get("Amount Awarded") or 0
            if existing is None or amt > existing_amt:
                prefix_lookup[prefix] = row

    return full_lookup, prefix_lookup


def _parse_wellcome_date(val: object) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        from datetime import datetime

        return datetime.strptime(str(val), "%Y-%m-%d").date()
    except ValueError:
        return None


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    try:
        full_lookup, prefix_lookup = _load_lookup(cache_dir, force_refresh)
    except Exception as exc:
        return AwardDetailsResult(
            found=[],
            not_found=[
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=aid,
                    reason=NotFoundReason.CACHE_ERROR,
                    detail=str(exc),
                )
                for aid in award_ids
            ],
        )

    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    for award_id in award_ids:
        norm = _normalize_wellcome(award_id)

        # Try exact match first.
        row = full_lookup.get(norm)

        # Fall back to numeric prefix lookup (handles bare 6-digit citations).
        if row is None:
            m = _NUMERIC_PREFIX_RE.match(norm)
            if m:
                row = prefix_lookup.get(m.group(1))

        if row is None:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="Not found in Wellcome Trust grants data",
                )
            )
            continue

        amount_raw = row.get("Amount Awarded")
        try:
            amount = float(amount_raw) if amount_raw is not None else None
        except (ValueError, TypeError):
            amount = None

        found.append(
            AwardDetails(
                funder_id=FUNDER_ID,
                award_id=award_id,
                amount_funded=amount,
                currency=str(row.get("Currency") or "GBP"),
                start_date=_parse_wellcome_date(row.get("Planned Dates:Start Date")),
                end_date=_parse_wellcome_date(row.get("Planned Dates:End Date")),
            )
        )

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    verified_awards=(
        "104169/Z/14/A",
        "211276/Z/18/Z",
        "203139/A/16/Z",
        "210753/Z/18/Z",
        "206194/Z/17/Z",
    ),
    matching_ids=(
        "106918/Z/15/Z",
        "077383/Z/05/Z",
        "108079/Z/15/Z",
        "214560/Z/18/Z",
        # WT-prefixed — normalised to numeric for lookup.
        "WT096185",
    ),
    not_found_awards=(),
    rejected_ids=(
        # FC-prefix (Cancer Research UK joint) — not in Wellcome bulk data.
        "FC001202",
        # NSF award.
        "1728743",
        # DOE award.
        "DE-SC0021358",
    ),
    extraction_texts=(
        ExtractionExample(
            text="Funded by Wellcome Trust grants 104169/Z/14/A and 211276/Z/18/Z.",
            expected_extracted=("104169/Z/14/A", "211276/Z/18/Z"),
            verified_existing=("104169/Z/14/A", "211276/Z/18/Z"),
        ),
    ),
)
