"""Funder matcher for the Deutsche Forschungsgemeinschaft (DFG)."""

import random
import re
import time
import urllib.parse
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from .._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from .._spec import ExtractionExample, FunderExamples
from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "dfg"
FUNDER_DISPLAY_NAME: str = "Deutsche Forschungsgemeinschaft"
FUNDER_ALTERNATE_IDS: tuple[str, ...] = ("dfg",)
FUNDER_ALTERNATE_NAMES: tuple[str, ...] = ("German Research Foundation",)
FUNDER_OPENALEX_ID: str = "F4320320879"
FUNDER_OPENALEX_ALTERNATE_IDS: tuple[str, ...] = ()

# Distinctive DFG programme codes only. Purely numeric GEPRIS project IDs
# are intentionally not matched here because they overlap with NSF/NSFC/
# CORDIS — callers with explicit DFG context should pass the funder
# directly rather than infer from a bare numeric string.
_DFG_RE = re.compile(
    r"\b(?:SFB-?TRR|SFB|TRR|FOR|EXC|GRK|RTG|SPP|INST)\s*\d+\b",
    re.IGNORECASE,
)

# 7-9 digit GEPRIS numeric project IDs embedded alongside programme codes.
_GEPRIS_EMBEDDED_RE = re.compile(r"\b(\d{7,9})\b")

# Matches a pure GEPRIS numeric ID (what extract_award_ids returns for embedded IDs).
_GEPRIS_NUMERIC_RE = re.compile(r"^\d{7,9}$")

_GEPRIS_BASE_URL = "https://gepris.dfg.de/gepris/projekt"
_GEPRIS_SEARCH_URL = "https://gepris.dfg.de/gepris/OCTOPUS"

_TERM_FROM_TO_RE = re.compile(r"Term from (\d{4}) to (\d{4})", re.IGNORECASE)
_TERM_SINCE_RE = re.compile(r"Term since (\d{4})", re.IGNORECASE)
_PROG_NUM_RE = re.compile(r"\d+")


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_DFG_RE.search(s))


def extract_award_ids(text: str) -> list[str]:
    s = normalize_dashes(text)
    seen: set[str] = set()
    results: list[str] = []

    for prog_match in _DFG_RE.finditer(s):
        ctx_start = max(0, prog_match.start() - 60)
        ctx_end = min(len(s), prog_match.end() + 60)
        context = s[ctx_start:ctx_end]

        prog_num_m = _PROG_NUM_RE.search(prog_match.group())
        prog_num = prog_num_m.group() if prog_num_m else ""

        gepris_ids = [
            n for n in _GEPRIS_EMBEDDED_RE.findall(context) if n != prog_num and len(n) >= 7
        ]

        if gepris_ids:
            for gid in gepris_ids:
                if gid not in seen:
                    seen.add(gid)
                    results.append(gid)
        else:
            prog_code = re.sub(r"\s+", "", prog_match.group().strip().upper())
            if prog_code not in seen:
                seen.add(prog_code)
                results.append(prog_code)

    return results


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; awardgetter; +https://github.com/evamaxfield/awardgetter)"
    )
    return session


def _make_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def _fetch_gepris_project(
    session: requests.Session, gepris_id: str
) -> tuple[AwardDetails | None, str | None]:
    url = f"{_GEPRIS_BASE_URL}/{gepris_id}?language=en"
    try:
        resp = session.get(url, timeout=15)
    except requests.exceptions.RequestException as exc:
        return None, str(exc)

    if resp.status_code == 404:
        return None, "not_found"
    if not resp.ok:
        return None, f"HTTP {resp.status_code}"

    soup = BeautifulSoup(resp.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    start_year: int | None = None
    end_year: int | None = None

    m = _TERM_FROM_TO_RE.search(page_text)
    if m:
        start_year = int(m.group(1))
        end_year = int(m.group(2))
    else:
        m = _TERM_SINCE_RE.search(page_text)
        if m:
            start_year = int(m.group(1))

    return (
        AwardDetails(
            funder_id=FUNDER_ID,
            award_id=gepris_id,
            amount_funded=None,
            currency="EUR",
            start_date=date(start_year, 1, 1) if start_year else None,
            end_date=date(end_year, 12, 31) if end_year else None,
        ),
        None,
    )


def _search_gepris_for_programme(driver: webdriver.Chrome, programme_code: str) -> str | None:
    query = re.sub(r"([A-Z]+)(\d+)", r"\1 \2", programme_code)
    params = urllib.parse.urlencode(
        {
            "task": "showSearchSimple",
            "context": "projekt",
            "keywords": query,
            "language": "en",
        }
    )
    driver.get(f"{_GEPRIS_SEARCH_URL}?{params}")
    try:
        WebDriverWait(driver, 10).until(
            expected_conditions.presence_of_element_located(
                (By.CSS_SELECTOR, "a[href*='/gepris/projekt/']")
            )
        )
        link = driver.find_element(By.CSS_SELECTOR, "a[href*='/gepris/projekt/']")
        href = link.get_attribute("href")
        m = re.search(r"/gepris/projekt/(\d+)", href or "")
        return m.group(1) if m else None
    except TimeoutException:
        return None


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    session = _make_session()
    driver = _make_driver()
    try:
        for award_id in award_ids:
            time.sleep(random.uniform(1.0, 2.0))

            gepris_id = award_id

            if not _GEPRIS_NUMERIC_RE.match(award_id):
                gepris_id_found = _search_gepris_for_programme(driver, award_id)
                if gepris_id_found is None:
                    not_found.append(
                        AwardNotFound(
                            funder_id=FUNDER_ID,
                            input_text=award_id,
                            reason=NotFoundReason.NOT_FOUND,
                            detail="No GEPRIS project found for programme code",
                        )
                    )
                    continue
                gepris_id = gepris_id_found

            details, error = _fetch_gepris_project(session, gepris_id)
            if details is None:
                not_found.append(
                    AwardNotFound(
                        funder_id=FUNDER_ID,
                        input_text=award_id,
                        reason=NotFoundReason.NOT_FOUND
                        if error == "not_found"
                        else NotFoundReason.API_ERROR,
                        detail=error or "Not found",
                    )
                )
                continue

            found.append(details)
    finally:
        driver.quit()

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/dfg_gepris_spec.md",
    verified_awards=(
        # Strings with embedded GEPRIS numeric project IDs — resolvable via direct page fetch.
        "SFB1423 / 421152132 - A07",
        "SFB-TRR 358/1 2023-491392403",
    ),
    matching_ids=(
        # Programme-code-only entries — require Selenium-based GEPRIS search to resolve.
        "SFB1114/A04",
        "SFB 1423",
        "EXC 2067/1 (MBExC)",
        "RTG 2070",
        "FOR 2975",
        "GRK2224",
        "SPP 2363",
        "INST 35/1134-1 FUGG",
    ),
    not_found_awards=(
        # Programme number 9999 does not exist in GEPRIS.
        "SFB9999",
        "EXC9999",
        "RTG9999",
    ),
    rejected_ids=(
        # Bare GEPRIS numeric IDs — explicitly excluded by the DFG matcher to
        # avoid colliding with NSF/NSFC/CORDIS. See awardgetter/funders/dfg.py.
        "39087428",
        "455548460",
        "460037581",
        "396611854",
        "460247524",
        # PI-style citation references — not GEPRIS programme codes.
        "HE 6166/17-1",
        "2315/11-1",
        # Free-text labels.
        "Deutsche Forschungsgemeinschaft (DFG)",
        "ORIGINS",
        # `BR` is not in the DFG programme alternation.
        "AFFA (BR 5207/1 and NI 369/15)",
        # Cross-funder distractors.
        "EP/S00923X/1",
        "DE-SC0021358",
        "ANR-21-CE29-0003",
    ),
    extraction_texts=(
        # Two embedded GEPRIS numeric IDs alongside programme codes — both verified.
        ExtractionExample(
            text=(
                "This project was funded by DFG through SFB1423 / 421152132 - A07"
                " and SFB-TRR 358/1 2023-491392403."
            ),
            expected_extracted=("421152132", "491392403"),
            verified_existing=("421152132", "491392403"),
        ),
        # Programme-code-only text — no GEPRIS ID in context, so codes are returned
        # directly (whitespace collapsed: "RTG 2070" → "RTG2070").
        ExtractionExample(
            text="Funded by DFG SFB1114/A04 and RTG 2070.",
            expected_extracted=("SFB1114", "RTG2070"),
            verified_existing=(),
        ),
    ),
)
