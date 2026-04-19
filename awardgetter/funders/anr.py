"""Funder matcher for the French Agence Nationale de la Recherche (ANR)."""

import re
from datetime import datetime
from pathlib import Path

import polars as pl

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._cache import get_cached_file
from .._spec import FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "anr"
FUNDER_DISPLAY_NAME: str = "Agence Nationale de la Recherche"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ()
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ("Agence nationale de la recherche",)

# Standard ANR reference: ANR-YY-XXXX-NNNN(-S), where XXXX is a 2-6 char
# programme code (CE##, JCJC, MRSEI, MPGA, LABX, EQPX, IDEX, INBS, NEUC,
# PCPA, ...).
_ANR_WITH_PREFIX_RE = re.compile(r"\bANR-\d{2}-[A-Z]{2,6}\d*-\d+(?:-\d+)?\b")

# No-prefix form seen in acknowledgements: 10-INBS-09-08, 16-IDEX-0004,
# 20-PCPA-0010. Only accept a closed set of programme codes so we don't
# false-match arbitrary date-like strings.
_ANR_NO_PREFIX_RE = re.compile(
    r"\b\d{2}-(?:LABX|EQPX|IDEX|INBS|NEUC|PCPA|JCJC|MRSEI|MPGA|CE\d+)-\d+(?:-\d+)?\b"
)

# Stable data.gouv.fr resource permalink URLs (redirect to latest file).
# Resource IDs are stable even when the underlying file is republished.
_ANR_DGDS_2010_URL = (
    "https://www.data.gouv.fr/fr/datasets/r/87d29a24-392e-4a29-a009-83eddcff3e66"
)
_ANR_DGDS_2010_FILENAME = "anr_dgds_depuis_2010.csv"

_ANR_DGDS_2009_URL = (
    "https://www.data.gouv.fr/fr/datasets/r/74a59cc0-ef79-458a-83e0-f181f9da459f"
)
_ANR_DGDS_2009_FILENAME = "anr_dgds_2005_2009.csv"

_ANR_PIA_URL = "https://www.data.gouv.fr/fr/datasets/r/aca6972b-577c-496a-aa26-009f81256dcb"
_ANR_PIA_FILENAME = "anr_pia.csv"

_ANR_CODE_COL = "Projet.Code_Decision"
_ANR_AMOUNT_COL = "Projet.Montant.AF.Aide_allouee.ANR"
_ANR_START_COL = "Projet.T0 scientifique"

# PIA/France-2030 CSV uses different column names from DGDS.
_ANR_PIA_CODE_COL = "Projet.Code_Decision_ANR"
_ANR_PIA_AMOUNT_COL = "Projet.Aide_allouee"
_ANR_PIA_START_COL = "Projet.Date_debut"

_ANR_PROJECT_NUM_RE = re.compile(r"^(ANR-\d{2}-[A-Z]{2,6}\d*-)(\d+)((?:-\d+)?)$")


def _anr_lookup_keys(ref: str) -> list[str]:
    """Return candidate lookup keys, including zero-padded project number variant."""
    ref = ref.upper()
    m = _ANR_PROJECT_NUM_RE.match(ref)
    if m:
        prefix, num, suffix = m.groups()
        padded = prefix + num.zfill(4) + suffix
        return [ref, padded] if padded != ref else [ref]
    return [ref]


def _parse_anr_amount(s: str | None) -> float | None:
    if not s:
        return None
    cleaned = (
        str(s).replace("€", "").replace("\xa0", "").replace(" ", "").replace(",", ".").strip()
    )
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_anr_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).strip()).date()
    except ValueError:
        return None


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_ANR_WITH_PREFIX_RE.search(s) or _ANR_NO_PREFIX_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    s = normalize_dashes(text)
    seen: set[str] = set()
    results: list[str] = []
    for m in _ANR_WITH_PREFIX_RE.finditer(s):
        val = m.group(0).upper()
        if val not in seen:
            seen.add(val)
            results.append(val)
    for m in _ANR_NO_PREFIX_RE.finditer(s):
        val = "ANR-" + m.group(0).upper()
        if val not in seen:
            seen.add(val)
            results.append(val)
    return results


def _load_anr_lookup(
    url: str,
    filename: str,
    cache_dir: Path,
    force_refresh: bool,
) -> tuple[dict[str, dict[str, str | None]], str | None]:
    """Download one ANR CSV and return a normalized code→{amount,start,end} lookup."""
    try:
        csv_path = get_cached_file(url, filename, cache_dir, force_refresh)
        df = pl.read_csv(
            csv_path,
            separator=";",
            infer_schema=False,
            ignore_errors=True,
            truncate_ragged_lines=True,
        )
    except Exception as exc:
        return {}, str(exc)

    if _ANR_CODE_COL in df.columns:
        code_col, amount_col, start_col = _ANR_CODE_COL, _ANR_AMOUNT_COL, _ANR_START_COL
        end_col: str | None = None
        for col in df.columns:
            col_lower = col.lower()
            if col != start_col and ("fin" in col_lower or "t_fin" in col_lower):
                end_col = col
                break
    elif _ANR_PIA_CODE_COL in df.columns:
        code_col, amount_col, start_col = (
            _ANR_PIA_CODE_COL,
            _ANR_PIA_AMOUNT_COL,
            _ANR_PIA_START_COL,
        )
        end_col = None
    else:
        return {}, None

    cols = [c for c in [code_col, amount_col, start_col, end_col] if c and c in df.columns]
    lookup: dict[str, dict[str, str | None]] = {}
    for row in df.select(cols).to_dicts():
        code = str(row.get(code_col) or "").strip().upper()
        if code:
            lookup[code] = {
                "amount": str(v) if (v := row.get(amount_col)) is not None else None,
                "start": str(v) if (v := row.get(start_col)) is not None else None,
                "end": str(v) if end_col and (v := row.get(end_col)) is not None else None,
            }
    return lookup, None


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    lookup: dict[str, dict[str, str | None]] = {}
    last_error: str | None = None

    for url, filename in [
        (_ANR_DGDS_2010_URL, _ANR_DGDS_2010_FILENAME),
        (_ANR_DGDS_2009_URL, _ANR_DGDS_2009_FILENAME),
        (_ANR_PIA_URL, _ANR_PIA_FILENAME),
    ]:
        partial, error = _load_anr_lookup(url, filename, cache_dir, force_refresh)
        if partial:
            lookup.update(partial)
        elif error:
            last_error = error

    if not lookup:
        for aid in award_ids:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=aid,
                    reason=NotFoundReason.CACHE_ERROR,
                    detail=last_error or "Failed to load ANR bulk CSV exports",
                )
            )
        return AwardDetailsResult(found=found, not_found=not_found)

    for award_id in award_ids:
        row = None
        for key in _anr_lookup_keys(award_id):
            row = lookup.get(key)
            if row is not None:
                break

        if row is None:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.NOT_FOUND,
                    detail="Reference not found in ANR bulk exports",
                )
            )
            continue

        found.append(
            AwardDetails(
                funder_id=FUNDER_ID,
                award_id=award_id,
                amount_funded=_parse_anr_amount(row.get("amount")),
                currency="EUR",
                start_date=_parse_anr_date(row.get("start")),
                end_date=_parse_anr_date(row.get("end")),
            )
        )

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/anr_spec.md",
    positive=(
        # Standard ANR competitive grants (DGDS) — `ANR-YY-CExx-NNNN[-S]`.
        "ANR-21-CE29-0003",
        "ANR-17-CE32-0006",
        "ANR-19-CE39-0007",
        "ANR-17-CE23-0012",
        "ANR-19-CE45-0010",
        "ANR-21-CE23-0006",
        "ANR-19-NEUC-0004",
        "ANR-18-CE40-0005",
        # PIA / France 2030 grants — `ANR-YY-PROG-NNNN[-S]`.
        "ANR-10-LABX-12-0",
        "ANR-10-LABX-24",
        "ANR-10-EQPX-29-0",
        "ANR-10-EQPX-03",
        "ANR-11-INBS-0013",
        "ANR-10-INBS-09-08",
        # No-prefix forms seen in acknowledgements.
        "10-INBS-09-08",
        "16-IDEX-0004",
        "20-PCPA-0010",
        # Multi-grant strings: a single hit anywhere in the text is sufficient.
        "ANR-10-EQPX-03 (Equipex) and ANR-10-INBS-09-08 (France Genomique Consortium)",
        "ANR GraVa ANR-18-CE40-0005",
    ),
    negative=(
        # Acronym-only references — not resolvable as ANR IDs.
        "CogFinAIgent",
        "OceaniX",
        # Truncated reference (no project number).
        "ANR-17-MPGA-",
        # Informal spacing — the current matcher does not normalise whitespace.
        "ANR10 LABX56",
        # Cross-funder distractors.
        "EP/S00923X/1",
        "DE-SC0021358",
        "62206216",
        "2022ZD0160401",
        "R01HL123456",
    ),
)
