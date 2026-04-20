#!/usr/bin/env python
"""CLI command to convert a CORDIS Project.jsonld dump to a compact Parquet lookup file."""

import json
from pathlib import Path
from typing import Annotated

import polars as pl
import typer

from .._constants import CORDIS_PARQUET_FILENAME, DEFAULT_CACHE_DIR

app = typer.Typer()

_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
_TYPE_PROJECT = "http://data.europa.eu/s66#Project"
_TYPE_MONETARY = "http://data.europa.eu/s66#MonetaryAmount"
_IDENTIFIER = "http://data.europa.eu/s66#identifier"
_START_DATE = "http://data.europa.eu/s66#startDate"
_END_DATE = "http://data.europa.eu/s66#endDate"
_HAS_TOTAL_COST = "http://data.europa.eu/s66#hasTotalCost"
_VALUE = "http://data.europa.eu/s66#value"


def _first_value(entity: dict, predicate: str) -> str | None:
    vals = entity.get(predicate, [])
    return vals[0]["value"] if vals else None


@app.command()
def preprocess_cordis(
    jsonld_path: Annotated[
        str, typer.Argument(help="Path to Project.jsonld from a CORDIS open-data dump")
    ],
    out_dir: Annotated[str, typer.Option(help="Output directory for the Parquet file")] = str(
        DEFAULT_CACHE_DIR
    ),
) -> None:
    """Convert a CORDIS Project.jsonld dump to a compact Parquet lookup file.

    Download the dump from the CORDIS open-data portal at
    cordis.europa.eu/en/projects/open-data, then run this command to generate
    the Parquet file that ec_cordis uses for award detail lookups.
    """
    _jsonld_path = Path(jsonld_path)
    _out_dir = Path(out_dir)

    if not _jsonld_path.exists():
        typer.echo(f"Error: file not found: {_jsonld_path}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Loading {_jsonld_path} (this may take a minute) …")
    with _jsonld_path.open() as f:
        data: dict = json.load(f)
    typer.echo(f"Loaded {len(data):,} top-level entities.")

    monetary: dict[str, str] = {}
    projects: list[dict] = []

    for uri, entity in data.items():
        type_uris = {v["value"] for v in entity.get(_TYPE, [])}

        if _TYPE_MONETARY in type_uris:
            val = _first_value(entity, _VALUE)
            if val is not None:
                monetary[uri] = val

        elif _TYPE_PROJECT in type_uris:
            project_id = _first_value(entity, _IDENTIFIER)
            if project_id is None:
                continue
            projects.append(
                {
                    "id": project_id,
                    "startDate": _first_value(entity, _START_DATE),
                    "endDate": _first_value(entity, _END_DATE),
                    "cost_uri": _first_value(entity, _HAS_TOTAL_COST),
                }
            )

    typer.echo(f"Found {len(monetary):,} monetary amounts and {len(projects):,} projects.")

    rows = [
        {
            "id": p["id"],
            "ecMaxContribution": monetary.get(p["cost_uri"]) if p["cost_uri"] else None,
            "startDate": p["startDate"],
            "endDate": p["endDate"],
        }
        for p in projects
    ]

    _out_dir.mkdir(parents=True, exist_ok=True)
    out_path = _out_dir / CORDIS_PARQUET_FILENAME
    pl.DataFrame(rows).write_parquet(out_path)
    typer.echo(f"Wrote {len(rows):,} rows to {out_path}")


def main() -> None:
    app()


if __name__ == "__main__":
    app()
