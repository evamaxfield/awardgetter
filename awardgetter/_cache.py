"""Shared bulk-file caching helper for funders that use CSV downloads."""

import time
from pathlib import Path

import requests


def get_cached_file(
    url: str,
    filename: str,
    cache_dir: Path,
    force_refresh: bool,
    max_age_days: int = 30,
) -> Path:
    """Return path to a cached file, downloading via chunked streaming if needed."""
    cache_path = cache_dir / filename
    cache_dir.mkdir(parents=True, exist_ok=True)
    needs_refresh = (
        force_refresh
        or not cache_path.exists()
        or (time.time() - cache_path.stat().st_mtime) > max_age_days * 86400
    )
    if needs_refresh:
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with cache_path.open("wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                f.write(chunk)
    return cache_path
