"""Structural interface every funder submodule must satisfy."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from ._award import AwardDetailsResult


@dataclass(frozen=True)
class FunderExamples:
    """Accept/reject award-id examples for a single funder matcher."""

    funder_id: str
    display_name: str
    source: str
    positive: tuple[str, ...]
    negative: tuple[str, ...]


@runtime_checkable
class FunderModule(Protocol):
    FUNDER_ID: str
    FUNDER_DISPLAY_NAME: str
    EXAMPLES: FunderExamples
    FUNDER_ALTERNATE_IDS: tuple[str, ...]
    FUNDER_ALTERNATE_NAMES: tuple[str, ...]

    @staticmethod
    def check_award_id(text: str) -> bool: ...

    @staticmethod
    def extract_award_ids(text: str) -> list[str]: ...

    @staticmethod
    def get_award_details(
        award_ids: list[str],
        cache_dir: Path,
        force_refresh: bool,
    ) -> AwardDetailsResult: ...
