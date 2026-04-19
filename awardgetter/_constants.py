"""Shared constants for cache locations and filenames."""

from pathlib import Path

DEFAULT_CACHE_DIR: Path = Path.home() / ".cache" / "awardgetter"
CORDIS_PARQUET_FILENAME: str = "cordis_projects.parquet"
