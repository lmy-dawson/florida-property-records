"""
Hillsborough County (Tampa) — 531,000+ parcels.

Source: https://downloads.hcpafl.org/ — free public bulk downloads, refreshed
daily. The page is ASP.NET WebForms, so the download links are __doPostBack
calls rather than hrefs; we fetch the page, lift the hidden form state and
replay the postback.

The payload is a ~100 MB zip holding a ~655 MB dBASE file, read as a stream so
memory stays flat.
"""

from __future__ import annotations

import html
import re
import struct
import zipfile
from typing import Iterator

import httpx

from ..normalize import clean, dbf_date, make_record

NAME = "Hillsborough"
LABEL = "Hillsborough County (Tampa)"
PORTAL = "https://downloads.hcpafl.org/"
FILE_MATCH = "HCparcel_4_public"
MEMBER = "parcel_4_public.dbf"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)


def _hidden(field: str, page: str) -> str:
    m = re.search(r'id="%s"[^>]*value="([^"]*)"' % field, page)
    return html.unescape(m.group(1)) if m else ""


def download(dest: str) -> str:
    with httpx.Client(timeout=900.0, follow_redirects=True,
                      headers={"User-Agent": UA}) as client:
        page = client.get(PORTAL).text

        rows = re.findall(
            r"__doPostBack\(&#39;([^&]+)&#39;,&#39;&#39;\)\"[^>]*>"
            r"(?:<i[^>]*></i>)?\s*([^<]+?)\s*</a>",
            page,
        )
        hit = next(((t, n) for t, n in rows if FILE_MATCH.lower() in n.lower()), None)
        if not hit:
            found = ", ".join(n for _, n in rows) or "nothing"
            raise RuntimeError(
                f"HCPA portal has no file matching {FILE_MATCH!r}. Found: {found}"
            )
        target, name = hit

        with client.stream(
            "POST", PORTAL,
            data={
                "__EVENTTARGET": target,
                "__EVENTARGUMENT": "",
                "__VIEWSTATE": _hidden("__VIEWSTATE", page),
                "__VIEWSTATEGENERATOR": _hidden("__VIEWSTATEGENERATOR", page),
                "__EVENTVALIDATION": _hidden("__EVENTVALIDATION", page),
            },
            headers={"Referer": PORTAL},
        ) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in resp.iter_bytes(1 << 20):
                    fh.write(chunk)
    return name


class _DBF:
    """Streaming dBASE reader. One forward pass, constant memory."""

    def __init__(self, fh):
        self.fh = fh
        header = fh.read(32)
        if len(header) < 32:
            raise ValueError("truncated DBF header")
        self.count, hlen, self.reclen = struct.unpack("<IHH", header[4:12])

        nfields = (hlen - 33) // 32
        self.slices: list[tuple[str, int, int]] = []
        offset = 1  # byte 0 of each record is the deletion flag
        for _ in range(nfields):
            fd = fh.read(32)
            name = fd[:11].rstrip(b"\x00").decode("latin-1")
            length = fd[16]
            self.slices.append((name, offset, offset + length))
            offset += length
        fh.read(hlen - 32 - nfields * 32)

    def __iter__(self) -> Iterator[dict]:
        reclen, slices = self.reclen, self.slices
        block = max(1, (8 << 20) // reclen) * reclen
        while True:
            buf = self.fh.read(block)
            if not buf:
                return
            for i in range(0, len(buf) - reclen + 1, reclen):
                rec = buf[i : i + reclen]
                if rec[0:1] == b"*":
                    continue
                yield {n: rec[a:b].decode("latin-1").strip() for n, a, b in slices}


def iter_records(path: str) -> Iterator[dict]:
    zf = zipfile.ZipFile(path)
    names = [n for n in zf.namelist() if n.lower().endswith(MEMBER)]
    if not names:
        dbfs = [n for n in zf.namelist() if n.lower().endswith(".dbf")]
        if not dbfs:
            raise RuntimeError("no .dbf inside the Hillsborough download")
        names = [max(dbfs, key=lambda n: zf.getinfo(n).file_size)]

    with zf.open(names[0]) as fh:
        for row in _DBF(fh):
            mailing = ", ".join(
                x for x in (clean(row.get("ADDR_1")), clean(row.get("ADDR_2"))) if x
            )
            yield make_record(
                county=LABEL,
                parcel_id=clean(row.get("FOLIO")),
                owner_name=clean(row.get("OWNER")),
                property_address=clean(row.get("SITE_ADDR")),
                property_city=clean(row.get("SITE_CITY")),
                property_zip=clean(row.get("SITE_ZIP")),
                mailing_address=mailing,
                mailing_city=clean(row.get("CITY")),
                mailing_state=clean(row.get("STATE")),
                mailing_zip=clean(row.get("ZIP")),
                just_value=row.get("JUST"),
                assessed_value=row.get("ASD_VAL"),
                taxable_value=row.get("TAX_VAL"),
                land_value=row.get("LAND"),
                building_value=row.get("BLDG"),
                last_sale_date=dbf_date(row.get("S_DATE")),
                last_sale_price=row.get("S_AMT"),
                beds=row.get("tBEDS"),
                baths=row.get("tBATHS"),
                living_area=row.get("HEAT_AR"),
                stories=row.get("tSTORIES"),
                units=row.get("tUNITS"),
                buildings=row.get("tBLDGS"),
                year_built=row.get("ACT"),
                effective_year_built=row.get("EFF"),
                acreage=row.get("ACREAGE"),
                land_use_code=clean(row.get("DOR_CODE")),
                land_use_description=clean(row.get("LU_GRP")),
                legal_description=" ".join(
                    clean(row.get(f"LEGAL{i}")) for i in (1, 2, 3, 4)
                ).strip(),
            )
