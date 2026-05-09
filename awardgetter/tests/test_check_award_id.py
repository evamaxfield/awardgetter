"""Per-funder accept/reject tests for `check_award_id` and `extract_award_ids`.

Each `FunderExamples` entry in `examples.FUNDER_EXAMPLES` is expanded into one
parametrized case per example string. Test IDs follow the pattern
``<funder_id>::<text>`` so a failing assertion in CI immediately identifies
both the matcher and the offending input.
"""

import pytest

from awardgetter._spec import ExtractionExample, FunderModule
from awardgetter.funders import (
    anr,
    arc,
    dfg,
    doe,
    ec_cordis,
    epsrc_ukri,
    jsps_kakenhi,
    nasa,
    nhmrc,
    nih,
    nkrdp,
    nsf,
    nsfc,
    onr,
    snsf,
    wellcome,
)

from .examples import FUNDER_EXAMPLES

FUNDER_MODULES: dict[str, FunderModule] = {
    m.FUNDER_ID: m
    for m in (
        anr,
        arc,
        dfg,
        doe,
        ec_cordis,
        epsrc_ukri,
        jsps_kakenhi,
        nasa,
        nih,
        nhmrc,
        nkrdp,
        nsf,
        nsfc,
        onr,
        snsf,
        wellcome,
    )
}


def _expand_accepts() -> list:
    """All examples that check_award_id should accept (format-valid in any category)."""
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


def _expand_rejects() -> list:
    """All examples that check_award_id should reject."""
    return [
        pytest.param(funder_id, text, id=f"{funder_id}::{text}")
        for funder_id, examples in FUNDER_EXAMPLES.items()
        for text in examples.rejected_ids
    ]


def _expand_extraction() -> list:
    """All ExtractionExample entries for extract_award_ids tests."""
    return [
        pytest.param(funder_id, ex, id=f"{funder_id}::{ex.text}")
        for funder_id, examples in FUNDER_EXAMPLES.items()
        for ex in examples.extraction_texts
    ]


def test_all_funders_satisfy_protocol() -> None:
    """Guard: every registered funder module must satisfy the FunderModule protocol."""
    from awardgetter._spec import FunderModule

    for funder in FUNDER_MODULES.values():
        assert isinstance(funder, FunderModule)


@pytest.mark.parametrize(("funder_id", "text"), _expand_accepts())
def test_check_award_id_accepts(funder_id: str, text: str) -> None:
    assert FUNDER_MODULES[funder_id].check_award_id(text) is True, (
        f"{funder_id}: expected check_award_id({text!r}) to return True"
    )


@pytest.mark.parametrize(("funder_id", "text"), _expand_rejects())
def test_check_award_id_rejects(funder_id: str, text: str) -> None:
    assert FUNDER_MODULES[funder_id].check_award_id(text) is False, (
        f"{funder_id}: expected check_award_id({text!r}) to return False"
    )


@pytest.mark.parametrize(("funder_id", "ex"), _expand_extraction())
def test_extract_award_ids(funder_id: str, ex: ExtractionExample) -> None:
    result = FUNDER_MODULES[funder_id].extract_award_ids(ex.text)
    assert result == list(ex.expected_extracted), (
        f"{funder_id}: extract_award_ids({ex.text!r}) returned {result!r}, "
        f"expected {list(ex.expected_extracted)!r}"
    )
