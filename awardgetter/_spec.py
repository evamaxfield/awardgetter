"""Structural interface every funder submodule must satisfy."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class FunderModule(Protocol):
    FUNDER_ID: str
    FUNDER_DISPLAY_NAME: str

    @staticmethod
    def check_award_id(text: str) -> bool: ...
