# awardgetter

A Python library for identifying which funding agency issued a given award ID string, and for fetching award metadata from those agencies.

The design is analogous to image-reading libraries like `imageio`: given an input string, the library tries to figure out which "reader" (funder) handles it. Since award ID formats can overlap across funders, `find_matching_funders` returns all plausible matches and lets the caller disambiguate — either by prompting the user or by accepting a known funder slug.

## Supported Funders

| `FUNDER_ID` | Display Name | Accepted Alternate IDs / Names | `get_award_details` |
|---|---|---|---|
| `nsf` | U.S. National Science Foundation | | Live API |
| `nih` | U.S. National Institutes of Health | `nci`, `nigms`, `niaid`, `nimh`, `nhlbi`, `niddk`, `ninds`, `nichd`, `nibib`, `nia`, `niehs`, `nidcd`, `nidcr`, `nida`, `niams`, `nei`, `ninr`, `nlm`, `fic`, `nccih`, `ncats` | Live API (NIH RePORTER) |
| `epsrc_ukri` | UK Research and Innovation (UKRI) | `epsrc`, `mrc`, `bbsrc`, `nerc`, `esrc`, `ahrc`, `stfc`, `ukri` | Live API (Gateway to Research) |
| `ec_cordis` | European Commission (CORDIS) | `cordis`, `ec`, `h2020`, `horizon`, `fp7` | Bulk parquet (see [Caching](#caching)) |
| `snsf` | Swiss National Science Foundation | `snf` | Bulk CSV |
| `anr` | Agence Nationale de la Recherche (France) | | Bulk CSV |
| `dfg` | Deutsche Forschungsgemeinschaft (Germany) | | Live API (GEPRIS) |
| `doe` | U.S. Department of Energy | | Live API (USASpending) |
| `jsps_kakenhi` | Japan Society for the Promotion of Science (KAKENHI) | `jsps`, `kakenhi` | Web scraping (KAKEN) |
| `nsfc` | National Natural Science Foundation of China | | Not implemented |
| `nkrdp` | National Key Research and Development Program of China | | Not implemented |

## Installation

Requires Python ≥ 3.12.

```bash
pip install awardgetter
```

## Quick Start

### Find which funders match an award ID

```python
from awardgetter import find_matching_funders

# Unambiguous: the "NSF" prefix makes this uniquely an NSF award
find_matching_funders("NSF 1728743")
# ['nsf']

# Unambiguous: the DE- prefix is specific to DOE
find_matching_funders("DE-SC0021358")
# ['doe']

# Ambiguous: bare 7-digit numbers match NSF, NSFC, and CORDIS formats
find_matching_funders("1728743")
# ['nsf', 'nsfc', 'ec_cordis']

# No match
find_matching_funders("not-an-award-id")
# []
```

### Fetch award details

```python
from awardgetter import get_award_details

result = get_award_details("nsf", "1728743")

for award in result.found:
    print(award.award_id)       # "1728743"
    print(award.amount_funded)  # 523456.0
    print(award.currency)       # "USD"
    print(award.start_date)     # datetime.date(2017, 9, 1)
    print(award.end_date)       # datetime.date(2021, 8, 31)

for miss in result.not_found:
    print(miss.reason)   # NotFoundReason.NOT_FOUND
    print(miss.detail)   # human-readable message
```

The `funder` argument is case-insensitive and accepts any alternate ID or name from the table above:

```python
get_award_details("National Science Foundation", "1728743")
get_award_details("NCI", "5R01CA123456-03")   # NIH institute alternate ID
get_award_details("EPSRC", "EP/L016796/1")    # UKRI council alternate ID
```

Multiple award IDs can be passed as a space- or comma-separated string:

```python
result = get_award_details("nih", "R01GM061300 U24NS124001")
print(len(result.found))      # 2
```

## API Reference

### `find_matching_funders(text) -> list[str]`

Returns the `FUNDER_ID` of every funder whose award ID pattern matches `text`. Returns an empty list if nothing matches. Multiple results are by design for ambiguous formats.

### `get_award_details(funder, award_id, cache_dir=None, force_refresh=False) -> AwardDetailsResult`

Fetches metadata for one or more award IDs from a specific funder.

| Parameter | Type | Description |
|---|---|---|
| `funder` | `str` | A `FUNDER_ID`, display name, or alternate ID (case-insensitive) |
| `award_id` | `str` | One or more award IDs (space- or comma-separated) |
| `cache_dir` | `Path \| None` | Override the default cache directory |
| `force_refresh` | `bool` | Re-download cached bulk data even if it is fresh |

### Return types

```python
@dataclass(frozen=True)
class AwardDetails:
    funder_id: str              # e.g. "nsf"
    award_id: str               # Normalized ID as returned by the funder
    amount_funded: float | None # Award amount in the funder's currency
    currency: str | None        # ISO 4217 code, e.g. "USD", "EUR", "CHF"
    start_date: date | None
    end_date: date | None

@dataclass(frozen=True)
class AwardNotFound:
    funder_id: str
    input_text: str        # The input that could not be resolved
    reason: NotFoundReason
    detail: str            # Human-readable explanation

@dataclass(frozen=True)
class AwardDetailsResult:
    found: list[AwardDetails]
    not_found: list[AwardNotFound]
```

`NotFoundReason` values:

| Value | Meaning |
|---|---|
| `NOT_FOUND` | Format is valid but the ID is not in the funder's database |
| `PARSE_ERROR` | No recognizable award ID could be extracted from the input |
| `API_ERROR` | Network or HTTP error when querying the funder's API |
| `CACHE_ERROR` | Problem loading the cached bulk data file |
| `RATE_LIMITED` | Funder API returned HTTP 429 |

## Caching

Funders that use bulk data files (CORDIS, SNSF, ANR) cache downloads under `~/.cache/awardgetter/` by default. Files are re-downloaded automatically after 30 days, or immediately when `force_refresh=True`.

**CORDIS requires a one-time setup step.** The CORDIS parquet file must be built from Horizon raw data before `get_award_details("ec_cordis", ...)` will work:

```bash
awardgetter-preprocess-cordis <path-to-cordis-json-ld-directory>
```

This places `cordis_projects.parquet` in the cache directory.

## Performance

Out of a sample of 4000 Award IDs, `awardgetter` was able to find the funded amount, and the start and end dates for ~75% of them.

| Funder | Total | Found | Success % |
|---|---|---|---|
| `nsf` | 1368 | 1229 | 89.8 |
| `snsf` | 157 | 129 | 82.2 |
| `anr` | 176 | 137 | 77.8 |
| `epsrc_ukri` | 177 | 134 | 75.7 |
| `nih` | 1155 | 772 | 66.8 |
| `ec_cordis` | 220 | 136 | 61.8 |
| `dfg` | 382 | 236 | 61.8 |
| `jsps_kakenhi` | 217 | 124 | 57.1 |
| `doe` | 148 | 83 | 56.1 |

_Awards requested with `awardgetter` were specifically those that OpenAlex didn't have the funded amount or start and date information for already._

## Development

```bash
just install   # install in editable mode with dev dependencies (uses uv)
just lint      # ruff check + format, then pyrefly type checking
just clean     # remove build artifacts

pytest awardgetter/tests/           # unit tests (no network)
just test.                          # integration tests (real API calls)
```

### Adding a new funder

1. Create `awardgetter/funders/<funder_id>.py` implementing the `FunderModule` protocol (`_spec.py`). Use `nsf.py` as the canonical example.
2. Import the module in `awardgetter/funders/__init__.py` and append it to `ALL_FUNDERS` (and `ALL_DETAIL_FUNDERS` if `get_award_details` is implemented).
3. Populate the `EXAMPLES` constant — parametrized tests in `test_check_award_id.py` and `test_get_award_details.py` expand automatically from it.

## License

MPL 2.0

## AI Usage Statement

While library structure and design decisions (e.g., mirroring the structure of image reading libraries), were deliberate design choices, much of the functionality of this library was developed using Claude Code. Retrieved award results were evaluated both by humans and AI.
