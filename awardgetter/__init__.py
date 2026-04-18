"""Top-level package for awardgetter."""

from importlib.metadata import PackageNotFoundError, version

from ._award import AwardDetails, AwardDetailsResult, AwardNotFound, NotFoundReason
from ._spec import FunderExamples, FunderModule
from .details import get_award_details
from .match import find_matching_funders

try:
    __version__ = version("awardgetter")
except PackageNotFoundError:
    __version__ = "uninstalled"

__author__ = "Eva Maxfield Brown"
__email__ = "evamaxfieldbrown@gmail.com"

__all__ = [
    "AwardDetails",
    "AwardDetailsResult",
    "AwardNotFound",
    "FunderExamples",
    "FunderModule",
    "NotFoundReason",
    "__version__",
    "find_matching_funders",
    "get_award_details",
]
