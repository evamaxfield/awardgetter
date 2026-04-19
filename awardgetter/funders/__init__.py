"""Registry of supported funder modules."""

from .._spec import FunderModule
from . import (
    anr,
    dfg,
    doe,
    ec_cordis,
    epsrc_ukri,
    jsps_kakenhi,
    nih,
    nkrdp,
    nsf,
    nsfc,
    snsf,
)

ALL_FUNDERS: tuple[FunderModule, ...] = (
    nsf,
    nih,
    nsfc,
    nkrdp,
    epsrc_ukri,
    ec_cordis,
    snsf,
    anr,
    dfg,
    doe,
    jsps_kakenhi,
)

ALL_DETAIL_FUNDERS: tuple[FunderModule, ...] = (
    nsf,
    nih,
    ec_cordis,
    snsf,
    epsrc_ukri,
    anr,
    doe,
    dfg,
)
