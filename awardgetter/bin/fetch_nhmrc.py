#!/usr/bin/env python
"""CLI command to download NHMRC grant outcome XLSX files from the NHMRC website.

The NHMRC outcomes page is JavaScript-rendered, so this script uses Selenium to
load the page, collect all XLSX download links, and cache the files locally.
The browser session cookies are forwarded to the download requests so that the
token-based download URLs are accepted by the server.

Requires: pip install 'awardgetter[nhmrc]'
"""

import re
import time
from pathlib import Path
from typing import Annotated

import requests
import typer

from .._constants import DEFAULT_CACHE_DIR

app = typer.Typer()

_NHMRC_OUTCOMES_URL = "https://www.nhmrc.gov.au/funding/data-research/outcomes"
_NHMRC_BASE_URL = "https://www.nhmrc.gov.au"
_YEAR_RE = re.compile(r"\b(20\d{2}|19\d{2})\b")
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@app.command()
def fetch_nhmrc(
    out_dir: Annotated[
        str,
        typer.Option(help="Output directory for cached XLSX files"),
    ] = str(DEFAULT_CACHE_DIR),
    force_refresh: Annotated[
        bool,
        typer.Option("--force-refresh", help="Re-download files that are already cached"),
    ] = False,
) -> None:
    """Download all NHMRC grant outcome XLSX files from the NHMRC website.

    Loads the NHMRC outcomes page with a headless Chrome browser, collects every
    .xlsx link, and downloads each file to OUT_DIR as nhmrc_grants_YYYY.xlsx.
    Browser session cookies are forwarded so that token-based download URLs work.

    Requires Selenium: pip install 'awardgetter[nhmrc]'
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError:
        typer.echo(
            "Error: selenium is required. Install with:\n"
            "  pip install 'awardgetter[nhmrc]'",
            err=True,
        )
        raise typer.Exit(1)

    _out_dir = Path(out_dir)
    _out_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Loading {_NHMRC_OUTCOMES_URL} with headless Chrome …")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={_USER_AGENT}")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    try:
        driver.get(_NHMRC_OUTCOMES_URL)
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(8)

        all_anchors = driver.find_elements(By.TAG_NAME, "a")

        xlsx_anchors = [
            a for a in all_anchors if a.get_attribute("data-file-extension") == "xlsx"
        ]
        if not xlsx_anchors:
            # Fallback: any anchor whose resolved href contains 'xlsx'.
            xlsx_anchors = [
                a for a in all_anchors if "xlsx" in (a.get_attribute("href") or "").lower()
            ]

        items: list[tuple[str, str]] = []
        seen_hrefs: set[str] = set()
        for link in xlsx_anchors:
            href = link.get_attribute("href") or ""
            if not href:
                continue
            if not href.startswith("http"):
                href = _NHMRC_BASE_URL + href
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)
            data_name = link.get_attribute("data-file-name") or ""
            items.append((href, data_name))

        # Capture browser cookies before closing — required for token download URLs.
        browser_cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
    finally:
        driver.quit()

    if not items:
        typer.echo("No XLSX links found on page. The page structure may have changed.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Found {len(items)} XLSX link(s).")

    session = requests.Session()
    session.headers["User-Agent"] = _USER_AGENT
    session.cookies.update(browser_cookies)

    for url, data_name in sorted(items):
        year_match = _YEAR_RE.search(data_name) or _YEAR_RE.search(url)
        if year_match:
            filename = f"nhmrc_grants_{year_match.group(1)}.xlsx"
        else:
            filename = data_name or url.rstrip("/").split("/")[-1]

        out_path = _out_dir / filename
        if out_path.exists() and not force_refresh:
            typer.echo(f"  {filename}: already cached, skipping")
            continue

        typer.echo(f"  Downloading {filename} …")
        resp = session.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with out_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        typer.echo(f"  Saved to {out_path}")
        time.sleep(0.5)

    typer.echo("Done. Run awardgetter queries with funder='nhmrc' to use the cached data.")


def main() -> None:
    app()


if __name__ == "__main__":
    app()
