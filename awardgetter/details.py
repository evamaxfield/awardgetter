"""Top-level dispatcher for award detail retrieval."""

from pathlib import Path

from ._award import AwardDetailsResult, AwardNotFound, NotFoundReason
from ._spec import FunderModule
from .funders import ALL_DETAIL_FUNDERS

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "awardgetter"


def _build_lookup() -> dict[str, FunderModule]:
    table: dict[str, FunderModule] = {}
    for mod in ALL_DETAIL_FUNDERS:
        for key in (
            mod.FUNDER_ID,
            mod.FUNDER_DISPLAY_NAME,
            *mod.FUNDER_ALTERNATE_IDS,
            *mod.FUNDER_ALTERNATE_NAMES,
        ):
            table[key.casefold()] = mod
    return table


_FUNDER_LOOKUP: dict[str, FunderModule] = _build_lookup()


def get_award_details(
    funder: str,
    award_id: str,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
) -> AwardDetailsResult:
    """Fetch award details from the specified funder.

    Parameters
    ----------
    funder:
        Funder slug (e.g. ``"nsf"``), alternate slug (e.g. ``"nci"``), or full
        display name (e.g. ``"National Science Foundation"``). Case-insensitive.
    award_id:
        Raw string containing one or more award IDs, potentially with surrounding
        prose or noise. The library extracts all recognizable IDs for the funder.
    cache_dir:
        Directory for cached bulk CSV files. Defaults to ``~/.cache/awardgetter``.
        Only used by funders that download bulk data (CORDIS, SNSF).
    force_refresh:
        If ``True``, re-download cached bulk files even if younger than 30 days.

    Returns
    -------
    AwardDetailsResult
        ``found`` contains one :class:`AwardDetails` per resolved award ID.
        ``not_found`` contains one :class:`AwardNotFound` per unresolved ID with
        a :class:`NotFoundReason` explaining why.

    Raises
    ------
    ValueError
        If ``funder`` does not match any registered detail funder.
    """
    mod = _FUNDER_LOOKUP.get(funder.casefold())
    if mod is None:
        supported = sorted({m.FUNDER_ID for m in ALL_DETAIL_FUNDERS})
        raise ValueError(f"Unknown funder {funder!r}. Supported funder IDs: {supported}")

    resolved_cache_dir = cache_dir if cache_dir is not None else _DEFAULT_CACHE_DIR

    extracted = mod.extract_award_ids(award_id)
    if not extracted:
        return AwardDetailsResult(
            found=[],
            not_found=[
                AwardNotFound(
                    funder_id=mod.FUNDER_ID,
                    input_text=award_id,
                    reason=NotFoundReason.PARSE_ERROR,
                    detail=f"No {mod.FUNDER_ID.upper()} award IDs found in input text",
                )
            ],
        )

    return mod.get_award_details(extracted, resolved_cache_dir, force_refresh)
