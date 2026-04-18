"""Structural interface every funder submodule must satisfy."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


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

    @staticmethod
    def check_award_id(text: str) -> bool: ...
