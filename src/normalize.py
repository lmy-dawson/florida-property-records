"""
Shared shaping for county parcel records.

Each county publishes its roll in its own format — Hillsborough ships a dBASE
file inside an ASP.NET portal, Pasco ships an 81 MB spreadsheet from a plain
HTTPS path — so every county module converts its rows into the single record
shape defined here. Anything a county does not publish comes out as null rather
than being invented.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

STREET_ABBR = {
    "STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR",
    "ROAD": "RD", "LANE": "LN", "COURT": "CT", "CIRCLE": "CIR",
    "PLACE": "PL", "TERRACE": "TER", "PARKWAY": "PKWY", "HIGHWAY": "HWY",
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
}

ENTITY_RE = re.compile(
    r"\b(LLC|L\.?L\.?C|INC|CORP|CORPORATION|LP|LLP|LTD|COMPANY|CO|HOLDINGS?|"
    r"GROUP|PARTNERS|CAPITAL|VENTURES?|ENTERPRISES?|PROPERTIES|INVESTMENTS?|"
    r"REALTY|TRUST|TRUSTEE|ESTATE|BANK|ASSOCIATION|CHURCH|AUTHORITY|DISTRICT|"
    r"COUNTY|CITY OF|STATE OF|DEPARTMENT)\b"
)

# Excel serial dates count from this epoch (the 1900 leap-year bug included).
EXCEL_EPOCH = date(1899, 12, 30)

SQFT_PER_ACRE = 43_560


def norm_addr(a: str | None) -> str:
    """Normalise a street address enough to compare mailing against situs."""
    cleaned = re.sub(r"[^A-Z0-9 ]", " ", (a or "").upper())
    return " ".join(STREET_ABBR.get(p, p) for p in cleaned.split()).strip()


def owner_type(name: str | None) -> str:
    return "entity" if ENTITY_RE.search((name or "").upper()) else "individual"


# Florida exempts certain owners from public disclosure — law enforcement,
# judges, victims of violence — and the counties publish a placeholder in place
# of the name. There is no owner data in these rows to deliver, and they are
# not people anyone should be building a marketing list from, so they are
# always dropped.
CONFIDENTIAL_RE = re.compile(r"CONFIDENTIAL|NOT DISCLOSED|EXEMPT PER (FS|F\.S)")


def is_confidential(name: str | None) -> bool:
    return bool(CONFIDENTIAL_RE.search((name or "").upper()))


def has_usable_address(addr: str | None) -> bool:
    """True when a site address could actually receive mail.

    County rolls carry a lot of parcels that have no street address at all —
    submerged land, rights of way, drainage tracts, conservation land. They
    show up as "", "0", or "0 EGMONT KEY", and they are noise for every use
    this data has.
    """
    a = (addr or "").strip()
    if not a or not re.search(r"[A-Za-z]", a):
        return False
    return not re.match(r"^0+(\s|$)", a)


def num(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace(",", ""))
    except ValueError:
        return None


def integer(v) -> int | None:
    f = num(v)
    return int(f) if f is not None else None


def dbf_date(v: str | None) -> str | None:
    """dBASE dates are YYYYMMDD strings."""
    v = (v or "").strip()
    if len(v) != 8 or not v.isdigit():
        return None
    try:
        return date(int(v[:4]), int(v[4:6]), int(v[6:8])).isoformat()
    except ValueError:
        return None


def excel_date(v) -> str | None:
    """Excel serial number -> ISO date. Also passes through real dates."""
    if v is None or v == "":
        return None
    if hasattr(v, "isoformat"):
        try:
            return v.date().isoformat() if hasattr(v, "date") else v.isoformat()
        except Exception:
            return None
    n = num(v)
    if not n or n <= 0 or n > 80000:
        return None
    try:
        return (EXCEL_EPOCH + timedelta(days=int(n))).isoformat()
    except (OverflowError, ValueError):
        return None


def clean(v) -> str:
    return str(v).strip() if v is not None else ""


# Each county writes its own land-use vocabulary — Hillsborough says
# "SINGLE FAMILY", Pasco says "Pkg Lot (Comm)" — so descriptions are mapped to
# one shared set of types. Order matters: the first matching rule wins, and
# VACANT is checked before the use it is vacant land *for*.
_TYPE_RULES = [
    ("Vacant Land",   ("VACANT", "VAC ")),
    ("Mobile Home",   ("MOBILE", "MH ", "MANUF HOME")),
    ("Condominium",   ("CONDO", "CO-OP", "COOP")),
    ("Single Family", ("SINGLE FAM", "SFR", "SINGLE-FAM")),
    ("Multi-Family",  ("MULTI", "APARTMENT", "APT", "DUPLEX", "TRIPLEX",
                       "QUADPLEX", "TOWNHOME", "TOWNHOUSE")),
    ("Agricultural",  ("AGRI", "FARM", "GROVE", "PASTURE", "TIMBER", "FOREST",
                       "CROP", "ORCHARD", "DAIRY", "POULTRY", "NURSERY")),
    ("Government",    ("GOVERNMENT", "MUNICIPAL", "COUNTY", "FEDERAL",
                       "STATE OWNED", "MILITARY", "PK/REC", "PARK")),
    ("Institutional", ("INSTITUT", "CHURCH", "SCHOOL", "HOSPITAL", "COLLEGE",
                       "ORPHAN", "CLUB", "CEMETER")),
    ("Industrial",    ("INDUS", "WAREHOUS", "MFG", "MANUFACT", "PACKING",
                       "LUMBER", "MINING")),
    ("Commercial",    ("COMM", "STORE", "OFFICE", "RETAIL", "SHOP", "RESTAUR",
                       "HOTEL", "MOTEL", "PKG", "PARKING", "SERVICE", "BANK",
                       "THEATER", "REPAIR", "FINANCIAL", "AUTO")),
]


def property_type(description: str | None) -> str:
    d = (description or "").upper()
    if not d:
        return "Other"
    for label, keys in _TYPE_RULES:
        if any(k in d for k in keys):
            return label
    return "Other"


def make_record(
    *,
    county: str,
    parcel_id: str,
    owner_name: str,
    property_address: str,
    property_city: str,
    property_zip: str,
    mailing_address: str,
    mailing_city: str,
    mailing_state: str,
    mailing_zip: str,
    just_value=None,
    assessed_value=None,
    taxable_value=None,
    land_value=None,
    building_value=None,
    last_sale_date=None,
    last_sale_price=None,
    beds=None,
    baths=None,
    living_area=None,
    stories=None,
    units=None,
    buildings=None,
    year_built=None,
    effective_year_built=None,
    lot_size_sqft=None,
    acreage=None,
    has_homestead=None,
    has_pool=None,
    land_use_code="",
    land_use_description="",
    legal_description="",
    previous_owner="",
) -> dict:
    """Assemble one normalised parcel record."""
    site_n = norm_addr(property_address)
    mail_n = norm_addr(mailing_address)
    absentee = bool(site_n and mail_n and not mail_n.startswith(site_n))

    jv = num(just_value)
    sale = num(last_sale_price)

    # Change in value since the last recorded sale. Deliberately NOT called
    # equity: public rolls carry no mortgage balance, so real equity is not
    # derivable from this data by anyone.
    appreciation = None
    if jv and sale and sale > 1000:
        appreciation = round((jv - sale) / jv * 100, 1)

    # Counties record land area in different units: Hillsborough publishes
    # acreage, Pasco publishes square feet. Each is converted to the other when
    # only one is present. The conversion is exact, so nothing is estimated, and
    # a parcel with neither stays null.
    lot_sqft = num(lot_size_sqft)
    acres = num(acreage)
    if not lot_sqft and acres:
        lot_sqft = acres * SQFT_PER_ACRE
    if not acres and lot_sqft:
        acres = round(lot_sqft / SQFT_PER_ACRE, 3)

    return {
        "parcelId": parcel_id,
        "county": county,
        "state": "FL",
        "ownerName": owner_name,
        "ownerType": owner_type(owner_name),
        "previousOwnerName": previous_owner or None,
        "propertyAddress": property_address,
        # Counties are inconsistent about case — Hillsborough ships both
        # "TAMPA" and "Tampa" — which silently breaks grouping and dedup for
        # anyone building a mailing list. Cities and states are upper-cased so
        # one place is always one value.
        "propertyCity": (property_city or "").upper(),
        "propertyZip": property_zip,
        "mailingAddress": mailing_address,
        "mailingCity": (mailing_city or "").upper(),
        "mailingState": (mailing_state or "").upper(),
        "mailingZip": mailing_zip,
        "isAbsenteeOwner": absentee,
        "isOutOfState": bool(mailing_state and mailing_state.upper() not in ("FL", "")),
        "hasHomesteadExemption": has_homestead,
        "justValue": jv,
        "assessedValue": num(assessed_value),
        "taxableValue": num(taxable_value),
        "landValue": num(land_value),
        "buildingValue": num(building_value),
        "lastSaleDate": last_sale_date,
        "lastSalePrice": sale,
        "appreciationSinceSalePct": appreciation,
        "beds": integer(beds),
        "baths": integer(baths),
        "livingAreaSqFt": integer(living_area),
        "stories": integer(stories),
        "residentialUnits": integer(units),
        "buildings": integer(buildings),
        "yearBuilt": integer(year_built),
        "effectiveYearBuilt": integer(effective_year_built),
        "lotSizeSqFt": integer(round(lot_sqft)) if lot_sqft else None,
        "acreage": acres,
        "hasPool": has_pool,
        "propertyType": property_type(land_use_description),
        "landUseCode": land_use_code,
        "landUseDescription": land_use_description,
        "legalDescription": legal_description,
    }
