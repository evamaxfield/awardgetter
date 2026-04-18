"""Public catalogue of award-id examples — aggregated from each funder module.

Each funder module in `awardgetter/funders/` exposes an `EXAMPLES` attribute
(a `FunderExamples` record) as part of its spec. This module collects them into
a single `FUNDER_EXAMPLES` dict for use in tests and by downstream consumers.

The catalogue is intentionally importable as part of the package so downstream
users — funder maintainers, data-curation pipelines, and scientists building
their own classifiers — can:

- reuse the example IDs as fixtures in their own test suites,
- audit which inputs each matcher recognises today,
- extend the catalogue when adding a new funder or shoring up an existing one.

To add or edit examples for a funder, edit the `EXAMPLES` constant in the
corresponding `awardgetter/funders/<id>.py` file.
"""

from .._spec import FunderExamples
from ..funders import ALL_FUNDERS

FUNDER_EXAMPLES: dict[str, FunderExamples] = {f.FUNDER_ID: f.EXAMPLES for f in ALL_FUNDERS}

__all__ = ["FUNDER_EXAMPLES", "FunderExamples"]
