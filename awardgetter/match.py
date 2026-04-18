"""Top-level dispatcher that asks every registered funder whether an
award-id string could plausibly be theirs."""

from .funders import ALL_FUNDERS


def find_matching_funders(text: str) -> list[str]:
    """Return `FUNDER_ID` for every registered funder whose pattern
    appears inside `text`. Order follows the registry in
    `awardgetter.funders.ALL_FUNDERS`. A string may legitimately match
    multiple funders (e.g. a bare 7-digit numeric string matches NSF,
    NSFC, and CORDIS); the caller resolves the ambiguity, optionally
    by supplying a known agency.
    """
    return [f.FUNDER_ID for f in ALL_FUNDERS if f.check_award_id(text)]
