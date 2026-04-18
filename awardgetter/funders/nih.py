"""Funder matcher for the U.S. National Institutes of Health (NIH)."""

import re

from .._text_cleaning import normalize_dashes

FUNDER_ID: str = "nih"
FUNDER_DISPLAY_NAME: str = "U.S. National Institutes of Health"

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


def check_award_id(text: str) -> bool:
    s = normalize_dashes(text)
    s = _NIH_BRACKETED_RE.sub(" ", s)
    s = _NIH_AGENCY_WORDS_RE.sub(" ", s)
    s = _NIH_SUPPL_RE.sub(" ", s)
    return bool(_NIH_CORE_PATTERN.search(s))
