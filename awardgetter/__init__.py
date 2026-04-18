"""Top-level package for awardgetter."""

from importlib.metadata import PackageNotFoundError, version

from ._spec import FunderModule
from .match import find_matching_funders

try:
    __version__ = version("awardgetter")
except PackageNotFoundError:
    __version__ = "uninstalled"

__author__ = "Eva Maxfield Brown"
__email__ = "evamaxfieldbrown@gmail.com"

__all__ = ["FunderModule", "__version__", "find_matching_funders"]
