"""Top-level package for awardgetter."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("awardgetter")
except PackageNotFoundError:
    __version__ = "uninstalled"

__author__ = "Eva Maxfield Brown"
__email__ = "evamaxfieldbrown@gmail.com"
