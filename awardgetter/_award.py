"""Public data types for award detail retrieval."""

import enum
from dataclasses import dataclass
from datetime import date


class NotFoundReason(enum.Enum):
    NOT_FOUND = "not_found"
    PARSE_ERROR = "parse_error"
    API_ERROR = "api_error"
    CACHE_ERROR = "cache_error"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True)
class AwardDetails:
    funder_id: str
    award_id: str
    amount_funded: float | None
    currency: str | None
    start_date: date | None
    end_date: date | None


@dataclass(frozen=True)
class AwardNotFound:
    funder_id: str
    input_text: str
    reason: NotFoundReason
    detail: str


@dataclass(frozen=True)
class AwardDetailsResult:
    found: list[AwardDetails]
    not_found: list[AwardNotFound]
