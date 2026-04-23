"""Shared text-normalization helpers used by funder matchers."""

import re

# U+2010 HYPHEN, U+2011 NON-BREAKING HYPHEN, U+2012 FIGURE DASH,
# U+2013 EN DASH, U+2014 EM DASH, U+2212 MINUS SIGN.
UNICODE_DASHES_CHARCLASS = "[\u2010\u2011\u2012\u2013\u2014\u2212]"
UNICODE_DASHES_RE = re.compile(UNICODE_DASHES_CHARCLASS)


def normalize_dashes(text: str) -> str:
    return UNICODE_DASHES_RE.sub("-", text)
