"""Shared text-normalization helpers used by funder matchers."""

import re

UNICODE_DASHES_CHARCLASS = "[\u2010\u2011\u2012\u2013\u2014\u2212]"
UNICODE_DASHES_RE = re.compile(UNICODE_DASHES_CHARCLASS)


def normalize_dashes(text: str) -> str:
    return UNICODE_DASHES_RE.sub("-", text)
