"""Funder matcher for the Deutsche Forschungsgemeinschaft (DFG)."""

import random
import re
import time
import urllib.parse
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

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
#
# Pattern logic (no IGNORECASE — DFG codes are uppercase in practice):
#   • 3-4 uppercase letters + optional space/dash + 3+ digits: covers SFB1114,
#     EXC-2189, RTG 2070, FOR 5249, etc.
#   • 2 uppercase letters + mandatory space/dash + 3+ digits: covers HE 6166
#     style PI-adjacent codes while excluding embedded substrings like SC in
#     DE-SC0021358 (no separator → no match).
#   • INST special case: mandatory separator, 2+ digits (INST 35/1134-1 FUGG).
# False positives are acceptable; the GEPRIS lookup will return NOT_FOUND.
_DFG_RE = re.compile(
    r"\b(?:[A-Z]{3,4}[-\s]*|[A-Z]{2}[-\s]+)\d{3,}(?!\d)"
    r"|\bINST[-\s]+\d{2,}(?!\d)",
    re.IGNORECASE,
)

# 7-9 digit GEPRIS numeric project IDs embedded alongside programme codes.
# Uses digit-only boundaries (not \b) so underscores don't block matching.
_GEPRIS_EMBEDDED_RE = re.compile(r"(?<!\d)(\d{7,9})(?!\d)")

# Bare 7-9 digit GEPRIS IDs (whole input) or "project ID XXXXXXXXX" form.
_GEPRIS_BARE_RE = re.compile(r"^\s*\d{7,9}\s*$")
_GEPRIS_ID_PREFIX_RE = re.compile(r"\bID\s+(\d{7,9})\b")

# Matches a pure GEPRIS numeric ID (what extract_award_ids returns for embedded IDs).
_GEPRIS_NUMERIC_RE = re.compile(r"^\d{7,9}$")

_GEPRIS_BASE_URL = "https://gepris.dfg.de/gepris/projekt"
_GEPRIS_SEARCH_URL = "https://gepris.dfg.de/gepris/OCTOPUS"

_TERM_FROM_TO_RE = re.compile(r"Term from (\d{4}) to (\d{4})", re.IGNORECASE)
_TERM_SINCE_RE = re.compile(r"Term since (\d{4})", re.IGNORECASE)
_PROG_NUM_RE = re.compile(r"\d+")

# Sub-project suffix: letter(s) + 1-3 digits optionally followed by a lowercase letter,
# e.g. B02, A04, C01, TP B05. Appears after the main programme code.
_DFG_SUBPROJECT_RE = re.compile(r"\b([A-Z]\d{1,3}[a-z]?)\b")
# Separator between encoded programme code and subproject (internal only).
_DFG_SUBPROJECT_SEP = "#"
_DFG_SUBPROJECT_ENCODED_RE = re.compile(r"^(.+)#([A-Z]\d{1,3}[a-z]?)$")
# Matches a subproject code in parentheses at the end of a GEPRIS h1, e.g. "(B02)".
_DFG_SUBPROJECT_IN_H1_RE_TEMPLATE = r"\({code}\)\s*$"


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    return bool(_DFG_RE.search(s))


def _collect_unique(items: list[str], seen: set[str], results: list[str]) -> None:
    for item in items:
        if item not in seen:
            seen.add(item)
            results.append(item)


def _extract_ids_from_programme(s: str, prog_match: re.Match) -> list[str]:
    ctx_start = max(0, prog_match.start() - 60)
    ctx_end = min(len(s), prog_match.end() + 60)
    context = s[ctx_start:ctx_end]
    prog_num_m = _PROG_NUM_RE.search(prog_match.group())
    prog_num = prog_num_m.group() if prog_num_m else ""
    gepris_ids = [
        n for n in _GEPRIS_EMBEDDED_RE.findall(context) if n != prog_num and len(n) >= 7
    ]
    if gepris_ids:
        return gepris_ids

    programme_code = re.sub(r"\s+", "", prog_match.group().strip().upper())

    # Look for a sub-project code in the text immediately after the programme match
    # (within 20 chars), e.g. "SFB 1449 B02" → encode as "SFB1449#B02".
    after = s[prog_match.end() : prog_match.end() + 20]
    sub_m = _DFG_SUBPROJECT_RE.search(after)
    if sub_m:
        return [programme_code + _DFG_SUBPROJECT_SEP + sub_m.group(1)]

    return [programme_code]


def extract_award_ids(text: str) -> list[str]:
    s = normalize_dashes(text)
    seen: set[str] = set()
    results: list[str] = []

    # Fast-path: whole string is a bare 7-9 digit GEPRIS ID.
    if _GEPRIS_BARE_RE.match(s):
        return [s.strip()]

    # "project ID XXXXXXXXX" or "ID XXXXXXXXX" pattern.
    _collect_unique(_GEPRIS_ID_PREFIX_RE.findall(s), seen, results)
    if results:
        return results

    for prog_match in _DFG_RE.finditer(s):
        _collect_unique(_extract_ids_from_programme(s, prog_match), seen, results)

    # Fallback: if no programme code found, extract any 7-9 digit number as a
    # potential GEPRIS ID (converts PARSE_ERROR → NOT_FOUND for bare numeric inputs).
    if not results:
        _collect_unique(_GEPRIS_EMBEDDED_RE.findall(s), seen, results)

    return results


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; awardgetter; +https://github.com/evamaxfield/awardgetter)"
    )
    return session


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


def _search_gepris_for_programme(session: requests.Session, programme_code: str) -> list[str]:
    """Return unique GEPRIS project IDs matching programme_code, or [] if none found."""
    query = re.sub(r"([A-Z]+)(\d+)", r"\1 \2", programme_code)
    params = urllib.parse.urlencode(
        {
            "task": "doSearchSimple",
            "context": "projekt",
            "keywords_criterion": query,
            "nurProjekteMitAB": "false",
            "language": "en",
        }
    )
    try:
        resp = session.get(f"{_GEPRIS_SEARCH_URL}?{params}", timeout=15)
    except requests.exceptions.RequestException:
        return []
    if not resp.ok:
        return []
    seen: list[str] = []
    for m in re.finditer(r'href="/gepris/projekt/(\d+)"', resp.text):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def _filter_candidates_by_programme_code(
    session: requests.Session,
    programme_code: str,
    candidates: list[str],
) -> list[str]:
    """Return candidates whose GEPRIS page has the programme code in the div.details h1.

    Only the umbrella project page carries the programme ID (e.g. 'SFB 1454') in the
    main h1 inside div.details. Sub-project pages show the sub-project title there
    instead and do not name the parent programme code in that element.
    """
    letter_m = re.match(r"([A-Za-z]+)", programme_code)
    number_m = re.search(r"(\d+)", programme_code)
    if not letter_m or not number_m:
        return candidates
    letters = re.escape(letter_m.group(1))
    number = re.escape(number_m.group(1))
    pattern = re.compile(rf"\b{letters}[\s\-]?{number}\b", re.IGNORECASE)

    matched = []
    for gepris_id in candidates:
        time.sleep(random.uniform(0.3, 0.6))
        url = f"{_GEPRIS_BASE_URL}/{gepris_id}?language=en"
        try:
            resp = session.get(url, timeout=15)
        except requests.exceptions.RequestException:
            continue
        if not resp.ok:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        h1 = soup.select_one("div.details h1")
        if h1 and pattern.search(h1.get_text(" ", strip=True)):
            matched.append(gepris_id)
    return matched


def _filter_candidates_by_subproject_code(
    session: requests.Session,
    subproject_code: str,
    candidates: list[str],
) -> list[str]:
    """Return candidates whose GEPRIS h1 ends with ({subproject_code}) in parentheses."""
    pattern = re.compile(
        _DFG_SUBPROJECT_IN_H1_RE_TEMPLATE.format(code=re.escape(subproject_code)),
        re.IGNORECASE,
    )
    matched = []
    for gepris_id in candidates:
        time.sleep(random.uniform(0.3, 0.6))
        url = f"{_GEPRIS_BASE_URL}/{gepris_id}?language=en"
        try:
            resp = session.get(url, timeout=15)
        except requests.exceptions.RequestException:
            continue
        if not resp.ok:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        h1 = soup.select_one("div.details h1")
        if h1 and pattern.search(h1.get_text(" ", strip=True)):
            matched.append(gepris_id)
    return matched


def _resolve_programme_to_gepris_id(
    session: requests.Session,
    award_id: str,
) -> tuple[str | None, AwardNotFound | None]:
    """Resolve a programme code (or programme#subproject) to a single GEPRIS project ID.

    Returns (gepris_id, None) on success or (None, AwardNotFound) on failure.
    """
    sub_m = _DFG_SUBPROJECT_ENCODED_RE.match(award_id)
    programme_code = sub_m.group(1) if sub_m else award_id
    subproject_code = sub_m.group(2) if sub_m else None

    candidates = _search_gepris_for_programme(session, programme_code)
    if not candidates:
        return None, AwardNotFound(
            funder_id=FUNDER_ID,
            input_text=award_id,
            reason=NotFoundReason.NOT_FOUND,
            detail="No GEPRIS project found for programme code",
        )

    if subproject_code:
        candidates = _filter_candidates_by_subproject_code(session, subproject_code, candidates)
        if not candidates:
            return None, AwardNotFound(
                funder_id=FUNDER_ID,
                input_text=award_id,
                reason=NotFoundReason.NOT_FOUND,
                detail=f"No GEPRIS project has ({subproject_code}) in its title",
            )
    elif len(candidates) > 1:
        candidates = _filter_candidates_by_programme_code(session, programme_code, candidates)
        if not candidates:
            return None, AwardNotFound(
                funder_id=FUNDER_ID,
                input_text=award_id,
                reason=NotFoundReason.NOT_FOUND,
                detail="No GEPRIS project has this programme code in its title",
            )

    if len(candidates) > 1:
        return None, AwardNotFound(
            funder_id=FUNDER_ID,
            input_text=award_id,
            reason=NotFoundReason.AMBIGUOUS,
            detail=f"Multiple GEPRIS projects match in h1: {', '.join(candidates)}",
        )
    return candidates[0], None


def get_award_details(
    award_ids: list[str],
    cache_dir: Path,
    force_refresh: bool,
) -> AwardDetailsResult:
    found: list[AwardDetails] = []
    not_found: list[AwardNotFound] = []

    session = _make_session()
    for award_id in award_ids:
        time.sleep(random.uniform(0.5, 1.0))

        if _GEPRIS_NUMERIC_RE.match(award_id):
            gepris_id: str = award_id
        else:
            resolved, error = _resolve_programme_to_gepris_id(session, award_id)
            if error is not None:
                not_found.append(error)
                continue
            assert resolved is not None
            gepris_id = resolved

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

    return AwardDetailsResult(found=found, not_found=not_found)


EXAMPLES = FunderExamples(
    funder_id=FUNDER_ID,
    display_name=FUNDER_DISPLAY_NAME,
    source="plans/dfg_gepris_spec.md",
    verified_awards=(
        # Strings with embedded GEPRIS numeric project IDs — resolvable via direct page fetch.
        "SFB1423 / 421152132 - A07",
        "SFB-TRR 358/1 2023-491392403",
        # Overall programme
        "SFB1423",
    ),
    matching_ids=(
        # Sub-project references — programme code + subproject suffix encoded as "CODE#SUB".
        "SFB 1449 B02",
        "CRC 1193 C04",
        # Programme-code-only entries — resolved via GEPRIS keyword search (doSearchSimple).
        "SFB1114/A04",
        "SFB 1423",
        "EXC 2067/1 (MBExC)",
        "RTG 2070",
        "FOR 2975",
        "GRK2224",
        "SPP 2363",
        "INST 35/1134-1 FUGG",
        # Hyphen between programme prefix and number (now accepted).
        "EXC-2189",
        # Mixed-case input — IGNORECASE handles it.
        "Sfb 951",
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
        # Digit-first references — no leading letter code.
        "2315/11-1",
        # Free-text labels.
        "Deutsche Forschungsgemeinschaft (DFG)",
        "ORIGINS",
        # Cross-funder distractors.
        # EP/... uses '/' separator which is not matched by [-\s]+.
        "EP/S00923X/1",
        # DE-SC...: 'SC' has no separator before the digits (no match for 2-letter+sep rule).
        "DE-SC0021358",
        # ANR-21: only 2 digits after the separator, below the 3-digit threshold.
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
        # Sub-project with slash separator — encoded as "PROGRAMME#SUBPROJECT".
        ExtractionExample(
            text="Funded by DFG SFB1114/A04 and RTG 2070.",
            expected_extracted=("SFB1114#A04", "RTG2070"),
            verified_existing=(),
        ),
        # Hyphen between programme prefix and number + underscore-separated GEPRIS ID.
        ExtractionExample(
            text="CIBSS - EXC-2189 - project ID 390939984",
            expected_extracted=("390939984",),
            verified_existing=(),
        ),
        # GEPRIS ID embedded after underscore — word-boundary fix required.
        ExtractionExample(
            text="FOR 5249_449872909",
            expected_extracted=("449872909",),
            verified_existing=(),
        ),
        # Sub-project reference — encoded as "PROGRAMME#SUBPROJECT".
        ExtractionExample(
            text="Funded by DFG CRC 1193 C04.",
            expected_extracted=("CRC1193#C04",),
            verified_existing=(),
        ),
    ),
)
