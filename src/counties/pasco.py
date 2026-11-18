"""
Pasco County — 326,000+ parcels.

Source: https://downloads.pascopa.com/ — the property appraiser publishes the
tax roll as plain HTTPS files with no portal state to negotiate. The parcel
summary is an ~81 MB zip containing a single large spreadsheet.

Unlike Hillsborough, Pasco publishes an explicit homestead-exemption flag,
which is a cleaner owner-occupancy signal than comparing addresses. It does not
publish bedroom or bathroom counts, so those come back null.
"""

from __future__ import annotations

import os
import zipfile
from typing import Iterator

import httpx
import openpyxl

from ..normalize import clean, excel_date, make_record

NAME = "Pasco"
LABEL = "Pasco County"
URL = "https://ftp01.pascopa.com/real_estate/parcel_summary.zip"
MEMBER = "parcel_summary.xlsx"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)


def download(dest: str) -> str:
    with httpx.stream(
        "GET", URL, timeout=900.0, follow_redirects=True,
        headers={"User-Agent": UA},
    ) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_bytes(1 << 20):
                fh.write(chunk)
    return os.path.basename(URL)


def _yes(v) -> bool | None:
    """Pasco writes Yes/No strings rather than booleans."""
    s = clean(v).upper()
    if s in ("Y", "YES", "TRUE", "1"):
        return True
    if s in ("N", "NO", "FALSE", "0"):
        return False
    return None


def iter_records(path: str) -> Iterator[dict]:
    # openpyxl cannot stream from inside a zip, so the sheet is extracted next
    # to the archive first and removed once the pass is done.
    work_dir = os.path.dirname(path) or "."
    with zipfile.ZipFile(path) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".xlsx")]
        if not members:
            raise RuntimeError("no .xlsx inside the Pasco download")
        member = members[0]
        zf.extract(member, work_dir)
    sheet_path = os.path.join(work_dir, member)

    try:
        wb = openpyxl.load_workbook(sheet_path, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = ws.iter_rows(values_only=True)

        header = next(rows, None)
        if not header:
            return
        idx = {str(h).strip(): i for i, h in enumerate(header) if h}

        def get(row, key):
            i = idx.get(key)
            return row[i] if i is not None and i < len(row) else None

        for row in rows:
            if not row:
                continue
            owner = " ".join(
                x for x in (clean(get(row, "OWNER_NAME_1")),
                            clean(get(row, "OWNER_NAME_2"))) if x
            )
            if not owner and not clean(get(row, "PARCEL")):
                continue

            mailing = ", ".join(
                x for x in (clean(get(row, "MAILING_ADDRESS_1")),
                            clean(get(row, "MAILING_ADDRESS_2"))) if x
            )
            yield make_record(
                county=LABEL,
                parcel_id=clean(get(row, "PARCEL")),
                owner_name=owner,
                property_address=clean(get(row, "SITE_ADDRESS")),
                property_city=clean(get(row, "SITE_CITY")),
                property_zip=clean(get(row, "SITE_ZIP")),
                mailing_address=mailing,
                mailing_city=clean(get(row, "MAILING_CITY")),
                mailing_state=clean(get(row, "MAILING_STATE")),
                mailing_zip=clean(get(row, "MAILING_ZIP")),
                just_value=get(row, "JUST_VALUE"),
                assessed_value=get(row, "ASSD_VAL_COUNTY"),
                taxable_value=get(row, "TAXABLE_VAL_COUNTY"),
                land_value=get(row, "LAND_VALUE"),
                building_value=get(row, "BUILDING_VALUE"),
                last_sale_date=excel_date(get(row, "SALE_DATE")),
                last_sale_price=get(row, "SALE_AMOUNT"),
                living_area=get(row, "LIVING_AREA"),
                units=get(row, "NUMBER_RESIDENTIAL_UNITS"),
                buildings=get(row, "NUMBER_BUILDINGS"),
                year_built=get(row, "ACTUAL_YEAR_BUILT"),
                effective_year_built=get(row, "EFFECTIVE_YEAR_BUILT"),
                lot_size_sqft=get(row, "LAND_SQ_FT"),
                has_homestead=_yes(get(row, "HAS_HOMESTEAD")),
                has_pool=_yes(get(row, "HAS_POOL")),
                land_use_code=clean(get(row, "LAND_USE_CODE")),
                land_use_description=clean(get(row, "LAND_USE_DESC")),
                legal_description=clean(get(row, "LEGAL_DESCRIPTION")),
                previous_owner=clean(get(row, "PREVIOUS_OWNER_NAME")),
            )
        wb.close()
    finally:
        try:
            os.remove(sheet_path)
        except OSError:
            pass
