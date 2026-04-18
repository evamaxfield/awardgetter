"""Funder matcher for European Commission research projects (CORDIS)."""

import re
from pathlib import Path

import polars as pl

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._cache import get_cached_file
from .._spec import FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "ec_cordis"
FUNDER_DISPLAY_NAME: str = "European Commission (CORDIS)"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ("cordis", "ec", "h2020", "horizon", "fp7")
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = (
    "European Commission",
    "European Research Council",
    "Horizon Europe",
    "Horizon 2020",
)

# CORDIS numeric project IDs range from ~6 digits (FP6/FP7) to 9 digits
# (Horizon Europe). Intentionally overlaps with NSF/NSFC for pure numerics.
_CORDIS_NUMERIC_RE = re.compile(r"\b\d{6,9}\b")

# Semicolon-delimited UTF-8 CSVs updated monthly from cordis.europa.eu.
# Verify these URLs if downloads fail — CORDIS occasionally reorganises them.
_CORDIS_CSVS = [
    (
        "https://cordis.europa.eu/data/cordis-HEprojects.csv",
        "cordis_he_projects.csv",
    ),
    (
        "https://cordis.europa.eu/data/cordis-h2020projects.csv",
        "cordis_h2020_projects.csv",
    ),
    (
        "https://cordis.europa.eu/data/cordis-fp7projects.csv",
        "cordis_fp7_projects.csv",
    ),
]


def _parse_cordis_date(s: str | None):
    if not s:
        return None
    from datetime import date

    try:
        return date.fromisoformat(str(s).strip())
    except ValueError:
        return None


def _build_cordis_lookup(cache_dir: Path, force_refresh: bool) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for url, filename in _CORDIS_CSVS:
        csv_path = get_cached_file(url, filename, cache_dir, force_refresh)
        df = pl.read_csv(csv_path, separator=";", infer_schema=False, ignore_errors=True)
        if "id" not in df.columns:
            continue
        cols = ["id", "ecMaxContribution", "startDate", "endDate"]
        for row in df.select(cols).to_dicts():
            row_id = str(row["id"]).strip()
            if row_id and row_id not in lookup:
                lookup[row_id] = row
    return lookup


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_CORDIS_NUMERIC_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    return _CORDIS_NUMERIC_RE.findall(normalize_dashes(text))


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    try:
        lookup = _build_cordis_lookup(cache_dir, force_refresh)
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

    for award_id in award_ids:
        row = lookup.get(award_id)
        if row is None:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="ID not found in CORDIS HE, H2020, or FP7 datasets",
                )
            )
            continue

        amount_raw = row.get("ecMaxContribution")
        try:
            amount = float(amount_raw) if amount_raw else None
        except (ValueError, TypeError):
            amount = None

        found.append(
            AwardDetails(
                funder_id=FUNDER_ID,
                award_id=award_id,
                amount_funded=amount,
                currency="EUR",
                start_date=_parse_cordis_date(row.get("startDate")),
                end_date=_parse_cordis_date(row.get("endDate")),
            )
        )

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/ec_cordis_spec.md",
    positive=(
        # Numeric CORDIS project IDs (6-9 digits, FP6 through Horizon Europe).
        "101069595",
        "101001318",
        "602150",
        "948381",
        # 6-digit IDs are valid CORDIS but the NSFC plan classifies the same
        # length as `unknown_short`. CORDIS owns 6-digit numerics here.
        "131060",
    ),
    negative=(
        # Acronyms — handled as low-confidence lookups in the spec, but not by
        # the current numeric-only matcher.
        "NEXTGENE",
        "GO-DS21",
        # Programme / call codes.
        "H2020-SC1",
        "H2020-MSCA-IF",
        "H2020RIA",
        "H2020-MSCA-IF-2020",
        "-MSCA-RISE-",
        # Programme names and external funder DOIs.
        "Destination Earth",
        "European Fund for Regional Development",
        "AEI/10.13039/501100011033",
        # Too short.
        "12345",
    ),
)
