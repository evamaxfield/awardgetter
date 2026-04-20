"""Structural interface every funder submodule must satisfy."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from ._award import AwardDetailsResult


@dataclass(frozen=True)
class ExtractionExample:
    """A structured example for testing the full extraction pipeline.

    Models the three-level flow: raw text → extracted IDs → API-verified subset.
    """

    text: str
    expected_extracted: tuple[str, ...]
    verified_existing: tuple[str, ...]


@dataclass(frozen=True)
class FunderExamples:
    """Award-id examples for a single funder matcher, grouped by testing purpose."""

    funder_id: str
    display_name: str
    source: str
    verified_awards: tuple[str, ...]
    matching_ids: tuple[str, ...]
    not_found_awards: tuple[str, ...]
    rejected_ids: tuple[str, ...]
    extraction_texts: tuple[ExtractionExample, ...]


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
