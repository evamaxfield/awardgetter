"""Funder matcher for the National Health and Medical Research Council (NHMRC, Australia)."""

import re
from datetime import date
from pathlib import Path

import polars as pl

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "nhmrc"
FUNDER_DISPLAY_NAME: str = "National Health and Medical Research Council"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ()
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ("NHMRC",)
FUNDER_OPENALEX_ID: str = "F4320334705"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ()

# APP and GNT are the two common citation prefixes; both wrap the same 7-digit integer.
_NHMRC_APP_RE = re.compile(r"\bAPP(\d{7})\b", re.IGNORECASE)
_NHMRC_GNT_RE = re.compile(r"\bGNT(\d{7})\b", re.IGNORECASE)

# Glob pattern for per-year cached files produced by awardgetter-fetch-nhmrc.
_NHMRC_CACHE_GLOB = "nhmrc_grants_*.xlsx"
_NHMRC_SHEET = "GRANTS DATA"

# Strip APP / GNT prefix to get the bare integer key used in the XLSX.
_PREFIX_RE = re.compile(r"^(?:APP|GNT)", re.IGNORECASE)


def _normalize_nhmrc(text: str) -> str:
    s = normalize_dashes(text).strip().lstrip("#")
    return _PREFIX_RE.sub("", s).strip()


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_NHMRC_APP_RE.search(s) or _NHMRC_GNT_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    s = normalize_dashes(text)
    seen: set[str] = set()
    results: list[str] = []
    for pattern in (_NHMRC_APP_RE, _NHMRC_GNT_RE):
        for m in pattern.finditer(s):
            val = m.group(0).upper()
            if val not in seen:
                seen.add(val)
                results.append(val)
    return results


def _load_lookup(cache_dir: Path) -> dict[str, dict]:
    """Load all nhmrc_grants_*.xlsx files and return a dict keyed by Application ID."""
    xlsx_files = sorted(cache_dir.glob(_NHMRC_CACHE_GLOB))
    if not xlsx_files:
        raise FileNotFoundError(
            f"No NHMRC grant files found in {cache_dir}. "
            "Run 'awardgetter-fetch-nhmrc' to download them."
        )

    frames: list[pl.DataFrame] = []
    for path in xlsx_files:
        try:
            df = pl.read_excel(path, sheet_name=_NHMRC_SHEET).select(
                [
                    "Application ID",
                    "Total amount awarded",
                    "Grant Start Date",
                    "Grant End Date",
                ]
            )
            frames.append(df)
        except Exception:
            continue

    combined = pl.concat(frames).unique(subset=["Application ID"], keep="last")
    return {str(row["Application ID"]): row for row in combined.to_dicts()}


def _parse_nhmrc_date(val: object) -> date | None:
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
        lookup = _load_lookup(cache_dir)
    except FileNotFoundError as exc:
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
        key = _normalize_nhmrc(award_id)
        row = lookup.get(key)

        if row is None:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="Not found in cached NHMRC grant data",
                )
            )
            continue

        amount_raw = row.get("Total amount awarded")
        try:
            amount = float(amount_raw) if amount_raw is not None else None
        except (ValueError, TypeError):
            amount = None

        found.append(
            AwardDetails(
                funder_id=FUNDER_ID,
                award_id=award_id,
                amount_funded=amount,
                currency="AUD",
                start_date=_parse_nhmrc_date(row.get("Grant Start Date")),
                end_date=_parse_nhmrc_date(row.get("Grant End Date")),
            )
        )

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    verified_awards=(
        "APP1196103",
        "APP1172917",
        "GNT1140976",
        "APP1107107",
    ),
    matching_ids=(
        "GNT1152807",
        "APP2010551",
        "GNT2025844",
    ),
    not_found_awards=(),
    rejected_ids=(
        # Bare 7-digit without APP/GNT prefix — ambiguous with NSF.
        "1046054",
        "1107107",
        # US federal contract number.
        "75F40121C00144",
        # NSF award.
        "1728743",
    ),
    extraction_texts=(
        ExtractionExample(
            text="This work was supported by NHMRC grants APP1196103 and GNT1140976.",
            expected_extracted=("APP1196103", "GNT1140976"),
            verified_existing=("APP1196103", "GNT1140976"),
        ),
    ),
)
