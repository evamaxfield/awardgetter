"""Funder matcher for JSPS KAKENHI grants."""

import random
import re
import time
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "jsps_kakenhi"
FUNDER_DISPLAY_NAME: str = "Japan Society for the Promotion of Science (KAKENHI)"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ("jsps", "kakenhi")
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = (
    "Japan Society for the Promotion of Science",
    "KAKENHI",
)
FUNDER_OPENALEX_ID: str = "F4320334764"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ()

# KAKENHI grant number: 2-digit fiscal year + letter code (H/K/J/L/N) +
# 5-digit serial. Optional JP citation prefix. Handles multi-id strings
# like "JP26282221, JP26120733, JP18H04037, and JP20H05955".
_KAKENHI_RE = re.compile(r"\b(?:JP)?\d{2}[HKJLN]\d{5}\b")

_KAKEN_GRANT_URL = "https://kaken.nii.ac.jp/grant/KAKENHI-PROJECT-{id}/"
# KAKEN website requests; 1.5s + jitter is conservative.
_KAKEN_RATE_LIMIT_SLEEP = 1.5


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_KAKENHI_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    s = normalize_dashes(text)
    raw = _KAKENHI_RE.findall(s)
    # Strip the JP citation prefix; the bare 8-char number is the API lookup key.
    return [r[2:] if r.startswith("JP") else r for r in raw]


def _parse_grant_page(html: str, award_id: str) -> AwardDetails:
    soup = BeautifulSoup(html, "html.parser")
    amount: float | None = None
    start_date: date | None = None
    end_date: date | None = None

    for th in soup.find_all("th"):
        label = th.get_text(strip=True)
        td = th.find_next_sibling("td")
        if td is None:
            continue

        if "Budget Amount" in label:
            m = re.search(r"¥([\d,]+)", td.get_text())
            if m:
                try:
                    amount = float(m.group(1).replace(",", ""))
                except ValueError:
                    pass

        elif "Project Period" in label:
            iso_dates = re.findall(r"\d{4}-\d{2}-\d{2}", td.get_text())
            if len(iso_dates) >= 2:
                try:
                    start_date = date.fromisoformat(iso_dates[0])
                    end_date = date.fromisoformat(iso_dates[1])
                except ValueError:
                    pass

    return AwardDetails(
        funder_id=FUNDER_ID,
        award_id=award_id,
        amount_funded=amount,
        currency="JPY",
        start_date=start_date,
        end_date=end_date,
    )


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    for i, award_id in enumerate(award_ids):
        if i > 0:
            time.sleep(_KAKEN_RATE_LIMIT_SLEEP + random.uniform(0.0, 0.5))

        lookup_id = award_id[2:] if award_id.startswith("JP") else award_id
        url = _KAKEN_GRANT_URL.format(id=lookup_id)

        try:
            resp = requests.get(url, timeout=30)
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
                    detail="Grant not found in KAKEN database",
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

        try:
            found.append(_parse_grant_page(resp.text, award_id))
        except Exception as exc:
            not_found.append(
                AwardNotFound(
                    funder_id=FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.PARSE_ERROR,
                    detail=f"Failed to parse KAKEN page: {exc}",
                )
            )

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    verified_awards=("22H00521",),
    matching_ids=(
        # Standard `YY` + letter code + 5-digit serial.
        "24K22291",
        "22H05118",
        "19H01891",
        "19K11852",
        "20H05951",
        "21J20930",
        "18K03693",
        "23H04869",
        "19H03696",
        "24K03119",
        # `JP` citation prefix — handled by the optional `(?:JP)?` group.
        "JP22K17712",
        "JP22H00516",
        # Multi-grant string — one hit is sufficient even when other tokens in
        # the string (e.g. JP26282221) are bare-numeric old-format grants the
        # current matcher does not recognise.
        "KAKENHI Grants JP26282221, JP26120733, JP18H04037, and JP20H05955",
    ),
    not_found_awards=(
        # Serial 99999 is extremely high and won't appear in KAKENHI records.
        "24K99999",
        "22H99999",
        "20N00000",
    ),
    rejected_ids=(
        # JST grants — different funder entirely.
        "JPMJSP2119",
        # Old purely-numeric KAKENHI numbers — not handled by the current regex
        # which requires the H/K/J/L/N letter code in the middle.
        "20002",
        "852010",
        # Truncated / wrong digit count.
        "19K2286",
        # Free-text labels.
        "KAKENHI Grant Number",
        "MEXT KAKENHI",
        "Advanced Research Netwo",
        # Cross-funder distractors.
        "EP/S00923X/1",
        "DE-SC0021358",
    ),
    extraction_texts=(
        # Standard IDs — bare 8-char returned (no JP prefix).
        ExtractionExample(
            text="22H05118 and 19K11852",
            expected_extracted=("22H05118", "19K11852"),
            verified_existing=(),
        ),
        # JP-prefixed IDs — prefix stripped in output.
        ExtractionExample(
            text="supported by JSPS KAKENHI JP22K17712 and JP22H00516",
            expected_extracted=("22K17712", "22H00516"),
            verified_existing=(),
        ),
        # Multi-grant string — only the letter-code IDs are extracted;
        # purely-numeric old-format IDs (JP26282221, JP26120733) are skipped.
        ExtractionExample(
            text="KAKENHI Grants JP26282221, JP26120733, JP18H04037, and JP20H05955",
            expected_extracted=("18H04037", "20H05955"),
            verified_existing=(),
        ),
    ),
)
