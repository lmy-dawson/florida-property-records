"""
Florida Property Records — Tampa Bay county parcel rolls.

Reads each county's official bulk export and emits one clean record per
parcel: owner name, owner MAILING address, physical property address, assessor
values, last recorded sale and building characteristics — with the filters
people actually search on (absentee owners, out-of-state owners, value bands,
property type, year built, sale recency).

All sources are free public records published by the county property
appraisers. No API keys, no logins, no paywalled resellers.
"""

from __future__ import annotations

import os
import tempfile

from apify import Actor

from .counties import ALL, COUNTIES
from .normalize import has_usable_address, is_confidential

class Filter:
    """Compiles the user's input once rather than re-reading it 858,000 times."""

    def __init__(self, cfg: dict):
        self.types = {t.strip().lower() for t in cfg.get("propertyTypes") or [] if t.strip()}
        self.cities = {c.strip().upper() for c in cfg.get("cities") or [] if c.strip()}
        self.zips = {z.strip()[:5] for z in cfg.get("zipCodes") or [] if z.strip()}
        self.absentee_only = bool(cfg.get("absenteeOwnersOnly"))
        self.out_of_state_only = bool(cfg.get("outOfStateOwnersOnly"))
        self.no_homestead_only = bool(cfg.get("excludeHomestead"))
        self.owner_type = cfg.get("ownerType") or "any"
        self.owner_contains = (cfg.get("ownerNameContains") or "").strip().upper()
        self.min_value = cfg.get("minJustValue")
        self.max_value = cfg.get("maxJustValue")
        self.min_year = cfg.get("minYearBuilt")
        self.max_year = cfg.get("maxYearBuilt")
        self.min_sqft = cfg.get("minLivingAreaSqFt")
        self.sold_before = cfg.get("lastSoldBeforeYear")
        self.sold_after = cfg.get("lastSoldAfterYear")
        self.require_address = cfg.get("requireValidAddress", True)

    def matches(self, r: dict) -> bool:
        # Always dropped: owners whose names are withheld under Florida's
        # public-records exemption. There is no owner data to deliver and they
        # are not appropriate marketing targets.
        if is_confidential(r["ownerName"]):
            return False
        # Parcels with no real street address — submerged land, rights of way,
        # drainage tracts — are ~5% of the roll and useless for every stated
        # use, so they are excluded unless explicitly asked for.
        if self.require_address and not has_usable_address(r["propertyAddress"]):
            return False
        if self.types and (r["propertyType"] or "").lower() not in self.types:
            return False
        if self.cities and (r["propertyCity"] or "").upper() not in self.cities:
            return False
        if self.zips and (r["propertyZip"] or "")[:5] not in self.zips:
            return False
        if self.absentee_only and not r["isAbsenteeOwner"]:
            return False
        if self.out_of_state_only and not r["isOutOfState"]:
            return False
        # Only meaningful where the county publishes the flag; parcels with no
        # homestead data are kept rather than silently dropped.
        if self.no_homestead_only and r["hasHomesteadExemption"] is True:
            return False
        if self.owner_type != "any" and r["ownerType"] != self.owner_type:
            return False
        if self.owner_contains and self.owner_contains not in (r["ownerName"] or "").upper():
            return False

        jv = r["justValue"]
        if self.min_value is not None and (jv is None or jv < self.min_value):
            return False
        if self.max_value is not None and (jv is None or jv > self.max_value):
            return False

        yb = r["yearBuilt"]
        if self.min_year is not None and (not yb or yb < self.min_year):
            return False
        if self.max_year is not None and (not yb or yb > self.max_year):
            return False

        if self.min_sqft is not None and (r["livingAreaSqFt"] or 0) < self.min_sqft:
            return False

        if self.sold_before is not None or self.sold_after is not None:
            if not r["lastSaleDate"]:
                return False
            year = int(r["lastSaleDate"][:4])
            if self.sold_before is not None and year >= self.sold_before:
                return False
            if self.sold_after is not None and year <= self.sold_after:
                return False

        return True


async def main() -> None:
    async with Actor:
        cfg = await Actor.get_input() or {}

        selected = [c for c in (cfg.get("counties") or ALL) if c in COUNTIES]
        if not selected:
            selected = ALL
        max_results = int(cfg.get("maxResults") or 1000)
        flt = Filter(cfg)

        Actor.log.info(
            f"Counties: {', '.join(selected)} | limit {max_results:,}"
        )

        # Billing needs no code here. The Actor is priced on Apify's built-in
        # events: a fixed fee when the run starts, then one charge per item
        # written to the default dataset, and the platform records both itself.
        # Explicit charge calls under custom event names used to sit here; they
        # matched no configured event and only put a warning in every run's log.

        tmp_dir = tempfile.mkdtemp()
        total_scanned = total_pushed = 0
        failures: list[str] = []

        for county_name in selected:
            if total_pushed >= max_results:
                break

            county = COUNTIES[county_name]
            archive = os.path.join(tmp_dir, f"{county_name.lower()}.zip")

            Actor.log.info(f"[{county.LABEL}] downloading the county parcel roll...")
            try:
                filename = county.download(archive)
            except Exception as exc:
                # One county being down should not lose the whole run.
                Actor.log.exception(f"[{county.LABEL}] download failed: {exc}")
                failures.append(county.LABEL)
                continue

            size_mb = os.path.getsize(archive) / 1e6
            Actor.log.info(f"[{county.LABEL}] got {filename} ({size_mb:.0f} MB), scanning...")

            scanned = pushed = 0
            batch: list[dict] = []
            try:
                for record in county.iter_records(archive):
                    scanned += 1
                    if scanned % 100_000 == 0:
                        Actor.log.info(
                            f"[{county.LABEL}] {scanned:,} scanned, {pushed:,} matched"
                        )

                    if not flt.matches(record):
                        continue

                    batch.append(record)
                    pushed += 1

                    if len(batch) >= 500:
                        await Actor.push_data(batch)
                        batch.clear()

                    if total_pushed + pushed >= max_results:
                        break

                if batch:
                    await Actor.push_data(batch)
            except Exception as exc:
                Actor.log.exception(f"[{county.LABEL}] failed while reading: {exc}")
                failures.append(county.LABEL)
            finally:
                try:
                    os.remove(archive)
                except OSError:
                    pass

            Actor.log.info(
                f"[{county.LABEL}] done — {scanned:,} scanned, {pushed:,} returned"
            )
            total_scanned += scanned
            total_pushed += pushed

        Actor.log.info(
            f"Finished. {total_scanned:,} parcels scanned, {total_pushed:,} returned."
        )

        if total_pushed == 0 and not failures:
            Actor.log.warning(
                "No parcels matched. Your filters may be too narrow — try widening "
                "the value range or clearing the city/ZIP filters."
            )
        if failures and total_pushed == 0:
            await Actor.fail(
                status_message="Every selected county failed to download: "
                + ", ".join(failures)
            )
        elif failures:
            Actor.log.warning(
                "Some counties could not be read and were skipped: "
                + ", ".join(failures)
            )
