"""Integration tests for `get_award_details` using each funder's positive examples.

Run with: pytest -m network -v
These tests make real network calls (APIs or bulk-CSV downloads).
"""

import shutil
import time
from pathlib import Path

import pytest
from flaky import flaky

from awardgetter import get_award_details
from awardgetter._constants import CORDIS_PARQUET_FILENAME, DEFAULT_CACHE_DIR
from awardgetter.funders import ALL_DETAIL_FUNDERS

from .examples import FUNDER_EXAMPLES

_DETAIL_FUNDER_IDS = {m.FUNDER_ID for m in ALL_DETAIL_FUNDERS}


@pytest.fixture(scope="session")
def cache_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("awardgetter_cache")
    src = DEFAULT_CACHE_DIR / CORDIS_PARQUET_FILENAME
    if src.exists():
        shutil.copy2(src, tmp / CORDIS_PARQUET_FILENAME)
    return tmp


def _expand_detail_positives() -> list:
    return [
        pytest.param(funder_id, text, id=f"{funder_id}::{text}")
        for funder_id, examples in FUNDER_EXAMPLES.items()
        if funder_id in _DETAIL_FUNDER_IDS
        for text in examples.positive
    ]


@pytest.mark.network
@flaky(max_runs=3, min_passes=1)
@pytest.mark.parametrize(("funder_id", "text"), _expand_detail_positives())
def test_get_award_details_finds_positive_example(
    funder_id: str, text: str, cache_dir: Path
) -> None:
    time.sleep(1)  # Be nice to APIs and avoid hitting rate limits
    result = get_award_details(funder_id, text, cache_dir=cache_dir)
    assert len(result.found) >= 1, (
        f"Expected at least one award found for {funder_id!r} / {text!r}; "
        f"got not_found={result.not_found}"
    )
    assert all(a.funder_id == funder_id for a in result.found)
