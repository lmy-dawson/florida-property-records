"""County registry.

Adding a county means writing one module exposing NAME, LABEL, download(dest)
and iter_records(path), then listing it here. Nothing else in the actor needs
to change.
"""

from . import hillsborough, pasco

COUNTIES = {
    hillsborough.NAME: hillsborough,
    pasco.NAME: pasco,
}

ALL = list(COUNTIES)
