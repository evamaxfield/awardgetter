"""Per-funder accept/reject tests for `check_award_id`.

Each `FunderExamples` entry in `examples.FUNDER_EXAMPLES` is expanded into one
parametrized case per example string. Test IDs follow the pattern
``<funder_id>::<text>`` so a failing assertion in CI immediately identifies
both the matcher and the offending input.
"""

import pytest

from awardgetter._spec import FunderModule
from awardgetter.funders import (
    anr,
    dfg,
    doe,
    ec_cordis,
    epsrc_ukri,
    jsps_kakenhi,
    nih,
    nkrdp,
    nsf,
    nsfc,
    snsf,
)

from .examples import FUNDER_EXAMPLES

FUNDER_MODULES: dict[str, FunderModule] = {
    m.FUNDER_ID: m
    for m in (anr, dfg, doe, ec_cordis, epsrc_ukri, jsps_kakenhi, nih, nkrdp, nsf, nsfc, snsf)
}


def _expand(kind: str) -> list:
    """Yield (funder_id, text) parametrize cases for `positive` or `negative`."""
    return [
        pytest.param(funder_id, text, id=f"{funder_id}::{text}")
        for funder_id, examples in FUNDER_EXAMPLES.items()
        for text in getattr(examples, kind)
    ]


def test_all_funders_satisfy_protocol() -> None:
    """Guard: every registered funder module must satisfy the FunderModule protocol."""
    from awardgetter._spec import FunderModule

    for funder in FUNDER_MODULES.values():
        assert isinstance(funder, FunderModule)


@pytest.mark.parametrize(("funder_id", "text"), _expand("positive"))
def test_check_award_id_accepts(funder_id: str, text: str) -> None:
    assert FUNDER_MODULES[funder_id].check_award_id(text) is True


@pytest.mark.parametrize(("funder_id", "text"), _expand("negative"))
def test_check_award_id_rejects(funder_id: str, text: str) -> None:
    assert FUNDER_MODULES[funder_id].check_award_id(text) is False
