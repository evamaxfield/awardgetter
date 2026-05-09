"""Registry of supported funder modules."""

from .._spec import FunderModule
from . import (
    anr,
    arc,
    dfg,
    doe,
    ec_cordis,
    epsrc_ukri,
    jsps_kakenhi,
    nasa,
    nhmrc,
    nih,
    nkrdp,
    nsf,
    nsfc,
    onr,
    snsf,
    wellcome,
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
    nasa,
    onr,
    arc,
    wellcome,
    nhmrc,
)

ALL_DETAIL_FUNDERS: tuple[FunderModule, ...] = (
    nsf,
    nih,
    epsrc_ukri,
    ec_cordis,
    snsf,
    anr,
    dfg,
    doe,
    jsps_kakenhi,
    nasa,
    onr,
    arc,
    wellcome,
    nhmrc,
)
