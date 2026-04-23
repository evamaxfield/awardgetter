"""Funder matcher for the Swiss National Science Foundation (SNSF)."""

import re
from pathlib import Path

import polars as pl

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._cache import get_cached_file
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "snsf"
FUNDER_DISPLAY_NAME: str = "Swiss National Science Foundation"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ("snf",)
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = (
    "Schweizerischer Nationalfonds",
    "Fonds national suisse",
    "Schweizerischer Nationalfonds zur Förderung der Wissenschaftlichen Forschung",
)
FUNDER_OPENALEX_ID: str = "F4320320924"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ()

# Covers known SNSF programme prefixes (Project Funding, NCCR, Sinergia,
# PRIMA, Ambizione, Postdoc Mobility, Early Postdoc Mobility, international,
# collaborative) followed by an underscore-, dash-, or space-separated number.
# Also covers older alphanumeric prefix formats not in the main list.
_SNSF_RE = re.compile(
    # Well-known SNSF programme prefixes — separator optional, serial 4-7 digits.
    r"\b(?:"
    r"200021L?|200020|51NF40|CRSII\d?|CRSK(?:-?\d)?|PP00P\d?|PP\d{4}|PZ00P\d?|PDFMP\d?"
    r"|PBZHP\d?|P\d{3}[A-Z]+|IZ[A-Z]+\d*|CR\d+I\d*"
    r")[_\s-]?\d{4,7}\b"
    # General alphanumeric prefix (TP500PN, TMAG-2, P5R5PB, P2ELP2) — mandatory separator
    # keeps false-positive rate low while catching novel SNSF programme series.
    # Underscore/hyphen: 4-7 digit serial. Space: 5-7 digits (prevents matching
    # 3-4 digit DFG programme codes like "EXC 2067").
    r"|\b[A-Z][A-Z0-9]{1,8}(?:-?\d)?(?:[_-]\d{4,7}| \d{5,7})\b"
    # Digit-heavy prefix with 1-2 letter suffix (32003B, 31003A, 3100A) — mandatory
    # separator; space allowed since these patterns are digit-first and unambiguous.
    r"|\b\d{4,6}[A-Z]{1,2}[_\s-]\d{5,7}\b"
    # Year+programme+call digit-starting prefix (20FI20, 10DL17, 33CS30) — mandatory separator.
    r"|\b\d{2}[A-Z]{2}\d{1,2}[_-]\d{5,7}\b"
    # Purely numeric composite IDs (205321-144529) — mandatory separator.
    r"|\b\d{5,6}[_-]\d{5,7}\b"
)

# Short pure-numeric IDs (5-6 digits) seen in older SNSF grants.
_SNSF_NUMERIC_RE = re.compile(r"\b\d{5,6}\b")

# Bulk CSV from the SNSF Data Portal. Verify this URL if downloads fail —
# the portal may update the export path.
_SNSF_CSV_URL = "https://data.snf.ch/datasets/grants.csv"
_SNSF_CSV_FILENAME = "snsf_grants.csv"

_STRIP_HASH_RE = re.compile(r"^#")
_STRIP_SUFFIX_RE = re.compile(r"/\d+$")
# Normalize the hyphen or space separator between programme prefix and numeric ID
# to underscore, which is the canonical form used in the SNSF bulk CSV.
_NORMALIZE_SEP_RE = re.compile(r"^([A-Z0-9]+)[-\s](\d)")
# Detect known SNSF programme prefixes concatenated directly with their serial (no separator),
# e.g. PZ00P2168016 → PZ00P2_168016. Must mirror the prefix list in _SNSF_RE.
_SNSF_PREFIX_DIRECT_RE = re.compile(
    r"^(200021L?|200020|51NF40|CRSII\d?|CRSK(?:-?\d)?|PP00P\d?|PP\d{4}|PZ00P\d?|PDFMP\d?"
    r"|PBZHP\d?|P\d{3}[A-Z]+|IZ[A-Z]+\d*|CR\d+I\d*)(\d{4,7})$"
)
# Strip SNF/SNSF keyword before matching — often appears before the grant number.
_SNSF_KEYWORD_RE = re.compile(r"\b(?:SNSF|SNF)\b", re.IGNORECASE)
# Extract the trailing numeric serial from a cleaned SNSF grant number.
_SNSF_SERIAL_SUFFIX_RE = re.compile(r"[_-](\d{5,7})$")


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
    # Insert underscore for known prefixes directly concatenated with their serial.
    m = _SNSF_PREFIX_DIRECT_RE.match(s)
    if m:
        return m.group(1) + "_" + m.group(2)
    s = _NORMALIZE_SEP_RE.sub(r"\1_\2", s)
    # Collapse any remaining internal space between alphanumeric and digit
    # (e.g. "CRSK_2 190840" → "CRSK_2_190840").
    s = re.sub(r"([A-Z0-9]) (\d)", r"\1_\2", s)
    return s


def _extract_serial(clean_id: str) -> str | None:
    """Return the trailing numeric serial from a cleaned SNSF grant number.

    '200021_166275' → '166275'; '166275' (bare numeric) → '166275'.
    """
    m = _SNSF_SERIAL_SUFFIX_RE.search(clean_id)
    if m:
        return m.group(1)
    if re.match(r"^\d{5,6}$", clean_id):
        return clean_id
    return None


def _normalize_snsf(text: str) -> str:
    s = normalize_dashes(text)
    s = s.lstrip("#")
    return _SNSF_KEYWORD_RE.sub(" ", s)


def check_award_id(text: str) -> bool:
    s = _normalize_snsf(text)
    return bool(_SNSF_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    s = _normalize_snsf(text)
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

    if "GrantNumber" not in df.columns:
        for aid in award_ids:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=aid,
                    reason=NotFoundReason.CACHE_ERROR,
                    detail="Unexpected CSV format: 'GrantNumber' column not found",
                )
            )
        return AwardDetailsResult(found=found, not_found=not_found)

    cols = [
        c
        for c in [
            "GrantNumber",
            "AmountGrantedAllSets",
            "EffectiveGrantStartDate",
            "EffectiveGrantEndDate",
        ]
        if c in df.columns
    ]
    lookup: dict[str, dict] = {
        str(row["GrantNumber"]).strip(): row
        for row in df.select(cols).to_dicts()
        if row.get("GrantNumber")
    }

    for award_id in award_ids:
        serial = _extract_serial(_clean_grant_number(award_id))
        row = lookup.get(serial) if serial else None
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
        # Space separator between prefix and serial (now accepted).
        "200021 137626",
        "CR23I2 138104",
        # Older alphanumeric prefix formats confirmed in SNSF bulk CSV.
        "32003B_159780",
        "31003A_179418",
        "P5R5PB_203169",
        "P2NEP2_191663",
        # Composite numeric prefix with hyphen separator.
        "205321-144529",
        # Missing separator — known prefix directly concatenated with serial.
        "PZ00P2168016",
        # CRSK programme series (CRSK-2 = phase indicator, space separator).
        "CRSK-2 190840",
        # PP + 4-digit variant (PP0022 style).
        "PP0022-118866",
        # Short (4-digit) serial numbers seen in older grants.
        "CRSII5_1835",
        # Novel programme prefixes caught by general alphanumeric pattern.
        "TP500PN_202741",
        "TMAG-2_209193",
        # Space separator between prefix and serial (now accepted by catch-all).
        "P2ELP2 187955",
        # Digit-heavy prefix with space separator.
        "3100A 132951/1",
        # SNF/SNSF keyword stripped before matching.
        "SNF 200021_178742",
        "SNSF PP00P3_170683",
        # Year+programme+call digit-starting prefixes (20FI20_, 10DL17_, 33CS30_).
        "20FI20_173691",
        "10DL17_183008",
        "33CS30_148415",
    ),
    not_found_awards=(
        # Serial 999999 does not appear in the SNSF bulk CSV.
        "200021_999999",
        "PP00P2_999999",
        "CRSII5_999999",
    ),
    rejected_ids=(
        # Programme umbrellas — not single grants.
        "NRP-77",
        "SNSF-ERC",
        "multiple",
        # Cross-funder distractors.
        "EP/S00923X/1",
    ),
    extraction_texts=(
        # Two underscore-separated SNSF grants in prose — underscore is a word char
        # so the numeric suffix has no leading \b and _SNSF_NUMERIC_RE won't over-extract.
        ExtractionExample(
            text="This research was supported by SNSF grants PZ00P3_180085 and PP00P2_138979.",
            expected_extracted=("PZ00P3_180085", "PP00P2_138979"),
            verified_existing=("PZ00P3_180085", "PP00P2_138979"),
        ),
        ExtractionExample(
            text="Funding from SNSF 200021_166275 and 200021_213074 enabled this study.",
            expected_extracted=("200021_166275", "200021_213074"),
            verified_existing=("200021_166275", "200021_213074"),
        ),
        # SNSF keyword is stripped before matching, so grant IDs are still extracted.
        ExtractionExample(
            text="SNSF grant 200021_166275 supported this work.",
            expected_extracted=("200021_166275",),
            verified_existing=("200021_166275",),
        ),
    ),
)
