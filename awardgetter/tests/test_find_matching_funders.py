"""Tests for the cross-funder dispatcher `find_matching_funders`.

Three layers of assertion:

1. Every catalogue positive must include its declared funder in the dispatch
   result. This guarantees the registry order in `awardgetter.funders` does
   not silently shadow a real match.
2. A hand-curated set of identifiers that — by their format alone — must
   resolve to exactly one funder.
3. A second hand-curated set documenting the *deliberate* ambiguity called
   out in `awardgetter.match`: bare numeric IDs in the 7-9 digit range are
   shared between NSF, NSFC and CORDIS by design.
"""

import pytest

from awardgetter import find_matching_funders

from .examples import FUNDER_EXAMPLES


def _expand_positives() -> list:
    params = []
    for funder_id, examples in FUNDER_EXAMPLES.items():
        for text in (
            *examples.verified_awards,
            *examples.matching_ids,
            *examples.not_found_awards,
        ):
            params.append(pytest.param(funder_id, text, id=f"{funder_id}::{text}"))
        for ex in examples.extraction_texts:
            params.append(pytest.param(funder_id, ex.text, id=f"{funder_id}::{ex.text}"))
    return params


@pytest.mark.parametrize(("funder_id", "text"), _expand_positives())
def test_positive_appears_in_dispatch(funder_id: str, text: str) -> None:
    assert funder_id in find_matching_funders(text)


# Format-distinctive identifiers that resolve to exactly one funder.
UNIQUE_MATCH_CASES: tuple[tuple[str, str], ...] = (
    ("EP/S00923X/1", "epsrc_ukri"),
    ("EP/L01663X", "epsrc_ukri"),
    ("MVSE EP/V002856/1", "epsrc_ukri"),
    ("DE-AC02-05CH11231", "doe"),
    ("DE-FG02-87ER40315", "doe"),
    ("ANR-10-LABX-12-0", "anr"),
    ("10-INBS-09-08", "anr"),
    ("2022ZD0160401", "nkrdp"),
    ("2020AAA0105601", "nkrdp"),
    ("2021QNRC001", "nkrdp"),
    ("PZ00P3_180085", "snsf"),
    ("CRSII5_205975", "snsf"),
    ("#51NF40_180888", "snsf"),
    ("24K22291", "jsps_kakenhi"),
    ("JP22K17712", "jsps_kakenhi"),
    ("21J20930", "jsps_kakenhi"),
    ("SFB1114/A04", "dfg"),
    ("EXC 2067/1 (MBExC)", "dfg"),
    ("GRK2224", "dfg"),
    ("R01HL123456", "nih"),
    ("T32GM007347", "nih"),
    ("5R01HL123456-05", "nih"),
    ("U1936210", "nsfc"),
    ("61661146007", "nsfc"),
)


@pytest.mark.parametrize(
    ("text", "expected_funder"),
    UNIQUE_MATCH_CASES,
    ids=[t for t, _ in UNIQUE_MATCH_CASES],
)
def test_unique_match(text: str, expected_funder: str) -> None:
    assert find_matching_funders(text) == [expected_funder]


# Deliberate overlaps. See awardgetter/match.py:11-14.
KNOWN_AMBIGUOUS_CASES: tuple[tuple[str, frozenset[str]], ...] = (
    # Bare 7-digit numerics: NSF (\d{7}), NSFC (\d{7,11}), CORDIS (\d{6,9}).
    ("2034901", frozenset({"nsf", "nsfc", "ec_cordis", "epsrc_ukri"})),
    ("1956322", frozenset({"nsf", "nsfc", "ec_cordis", "epsrc_ukri"})),
    # 6-digit numerics: only CORDIS (\d{6,9}).
    ("948381", frozenset({"ec_cordis"})),
    ("602150", frozenset({"ec_cordis"})),
    # 8-digit numerics: NSFC (\d{7,11}) and CORDIS (\d{6,9}); NSF needs exactly 7.
    ("62206216", frozenset({"nsfc", "ec_cordis"})),
    ("101069595", frozenset({"nsfc", "ec_cordis"})),
    # Hyphenated NSFC ID: NSFC matches the 8-digit prefix, CORDIS too.
    ("20221279-ZKT03", frozenset({"nsfc", "ec_cordis"})),
    # DoE ID also matches NSF: letter-prefix stripping yields 7-digit 0021358.
    ("DE-SC0021358", frozenset({"nsf", "doe"})),
    # ANR programme codes also match SNSF's broad catch-all (CE29-0003 fits the pattern).
    ("ANR-21-CE29-0003", frozenset({"snsf", "anr"})),
    # IDEX-0004 matches SNSF and DFG catch-alls in addition to ANR.
    ("16-IDEX-0004", frozenset({"snsf", "anr", "dfg"})),
)


@pytest.mark.parametrize(
    ("text", "expected_set"),
    KNOWN_AMBIGUOUS_CASES,
    ids=[t for t, _ in KNOWN_AMBIGUOUS_CASES],
)
def test_known_ambiguous(text: str, expected_set: frozenset[str]) -> None:
    assert set(find_matching_funders(text)) == expected_set
