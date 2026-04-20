"""Funder matcher for the Swiss National Science Foundation (SNSF)."""

import re
from pathlib import Path

import polars as pl

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._cache import get_cached_file
from .._spec import FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "snsf"
FUNDER_DISPLAY_NAME: str = "Swiss National Science Foundation"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ("snf",)
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = (
    "Schweizerischer Nationalfonds",
    "Fonds national suisse",
)

# Covers known SNSF programme prefixes (Project Funding, NCCR, Sinergia,
# PRIMA, Ambizione, Postdoc Mobility, Early Postdoc Mobility, international,
# collaborative) followed by an underscore- or dash-separated number.
_SNSF_RE = re.compile(
    r"\b(?:"
    r"200021L?|200020|51NF40|CRSII\d?|PP00P\d?|PZ00P\d?|PDFMP\d?"
    r"|PBZHP\d?|P\d{3}[A-Z]+|IZ[A-Z]+\d*|CR\d+I\d*"
    r")[_-]?\d+\b"
)

# Short pure-numeric IDs (5-6 digits) seen in older SNSF grants.
_SNSF_NUMERIC_RE = re.compile(r"\b\d{5,6}\b")

# Bulk CSV from the SNSF Data Portal. Verify this URL if downloads fail —
# the portal may update the export path.
_SNSF_CSV_URL = "https://data.snf.ch/public_storage/datasets/Grant.csv"
_SNSF_CSV_FILENAME = "snsf_grants.csv"

_STRIP_HASH_RE = re.compile(r"^#")
_STRIP_SUFFIX_RE = re.compile(r"/\d+$")
# Normalize the hyphen separator between programme prefix and numeric ID to
# underscore, which is the canonical form used in the SNSF bulk CSV.
_NORMALIZE_SEP_RE = re.compile(r"^([A-Z0-9]+)-(\d)")


def _parse_snsf_date(s: str | None):
    if not s:
        return None
    from datetime import datetime

    raw = str(s).strip().rstrip("Z")
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def _clean_grant_number(raw: str) -> str:
    s = _STRIP_HASH_RE.sub("", raw.strip())
    s = _STRIP_SUFFIX_RE.sub("", s)
    return _NORMALIZE_SEP_RE.sub(r"\1_\2", s)


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    s = s.lstrip("#")
    return bool(_SNSF_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    s = normalize_dashes(text)
    matches = _SNSF_RE.findall(s) + _SNSF_NUMERIC_RE.findall(s)
    return [_clean_grant_number(m) for m in matches]


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    try:
        csv_path = get_cached_file(_SNSF_CSV_URL, _SNSF_CSV_FILENAME, cache_dir, force_refresh)
        df = pl.read_csv(
            csv_path,
            separator=";",
            infer_schema=False,
            ignore_errors=True,
            truncate_ragged_lines=True,
        )
    except Exception as exc:
        for aid in award_ids:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=aid,
                    reason=NotFoundReason.CACHE_ERROR,
                    detail=str(exc),
                )
            )
        return AwardDetailsResult(found=found, not_found=not_found)

    if "GrantNumberString" not in df.columns:
        for aid in award_ids:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=aid,
                    reason=NotFoundReason.CACHE_ERROR,
                    detail="Unexpected CSV format: 'GrantNumberString' column not found",
                )
            )
        return AwardDetailsResult(found=found, not_found=not_found)

    cols = [
        c
        for c in [
            "GrantNumberString",
            "AmountGrantedAllSets",
            "EffectiveGrantStartDate",
            "EffectiveGrantEndDate",
        ]
        if c in df.columns
    ]
    lookup: dict[str, dict] = {
        _clean_grant_number(str(row["GrantNumberString"])): row
        for row in df.select(cols).to_dicts()
        if row.get("GrantNumberString")
    }

    for award_id in award_ids:
        row = lookup.get(_clean_grant_number(award_id))
        if row is None:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="Grant number not found in SNSF bulk export",
                )
            )
            continue

        amount_raw = row.get("AmountGrantedAllSets")
        try:
            amount = float(amount_raw) if amount_raw else None
        except (ValueError, TypeError):
            amount = None

        found.append(
            AwardDetails(
                funder_id=FUNDER_ID,
                award_id=_clean_grant_number(award_id),
                amount_funded=amount,
                currency="CHF",
                start_date=_parse_snsf_date(row.get("EffectiveGrantStartDate")),
                end_date=_parse_snsf_date(row.get("EffectiveGrantEndDate")),
            )
        )

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/snsf_spec.md",
    verified_awards=(
        # Programme-prefixed grant numbers confirmed in SNSF bulk CSV.
        "PZ00P3_180085",
        "PDFMP3-130309",
        "51NF40_141869",
        "200021_181978/1",
        "CRSII5_205975",
        "IZRJZ3_164171",
        "200021_166275",
        "PP00P2_138979",
        "200021_213074",
        "200021L_212718",
        "CR22I2_166110",
        "P400PB_199242",
    ),
    matching_ids=(
        # Leading `#` is stripped before matching.
        "#51NF40_180888",
        # Grant number embedded in a descriptive label.
        "Prospective Researcher Fellowship, PBZHP2-147259",
    ),
    not_found_awards=(),
    rejected_ids=(
        # Programme umbrellas — not single grants.
        "NRP-77",
        "SNSF-ERC",
        "multiple",
        # Bare older-format numeric IDs are not handled by the current matcher
        # (it requires a programme prefix). Documented gap.
        "192079",
        "178220",
        "955606",
        # Cross-funder distractors.
        "EP/S00923X/1",
        "DE-SC0021358",
        "ANR-21-CE29-0003",
    ),
    extraction_texts=(),
)
