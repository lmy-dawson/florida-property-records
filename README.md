[![tests](https://github.com/lmy-dawson/florida-property-records/actions/workflows/tests.yml/badge.svg)](https://github.com/lmy-dawson/florida-property-records/actions/workflows/tests.yml)

> **Live tool:** [apify.com/teamsasuke/florida-property-records](https://apify.com/teamsasuke/florida-property-records) — running in production on the Apify Store.
> Source code by [Benjamin-David Dawson](https://github.com/lmy-dawson). The rest of this README is the user guide shown on the Store.

<details>
<summary><b>For developers: how it works and how to run it</b></summary>

**Stack:** Python 3.12, httpx, openpyxl, Apify SDK, Docker

- `src/counties/` — one adapter per county (Hillsborough, Pasco) that reads the county's public parcel data.
- `src/normalize.py` — maps both counties into one schema (owner, mailing address, assessed value, sales, building data) and converts lot size between acres and square feet so both counties fill the same fields.
- Filters such as absentee owners and sale dates run before output; results go to an Apify dataset, which exports as JSON, CSV or Excel.

**Run the tests:** `pip install -r requirements.txt pytest && pytest`

**Run locally**

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scriptsctivate
pip install -r requirements.txt
mkdir -p storage/key_value_stores/default
# put your input in storage/key_value_stores/default/INPUT.json (schema: .actor/input_schema.json)
APIFY_LOCAL_STORAGE_DIR=./storage python -m src
```

Results are written to `storage/datasets/default/`. On the Apify platform the same code runs in the Docker image defined by `Dockerfile`.

</details>

---

# Florida Property Records Scraper — Owner, Absentee, Tax & Sale Data

**858,000+ Florida parcels** with the owner's name, the owner's **mailing
address**, the physical property address, assessor values, sale history and
building characteristics.

Straight from each county property appraiser's own bulk export. No API key, no
login, no third-party data reseller in the middle — and no monthly subscription
to a property data platform.

**Counties covered:** Hillsborough (531k parcels) and Pasco (326k parcels) —
Tampa, Brandon, Riverview, Plant City, Valrico, Lutz, Temple Terrace, Ruskin,
Apollo Beach, New Port Richey, Wesley Chapel, Land O' Lakes, Zephyrhills,
Hudson and Dade City.

## What people use this for

- **Absentee owner lists.** One switch returns only parcels where the owner's
  mailing address differs from the property address. Both addresses come from
  the tax roll, so it is exact rather than inferred.
- **Out-of-state owner leads.** Separate switch for owners who receive mail
  outside Florida.
- **Direct mail campaigns.** Every record carries a deliverable owner mailing
  address taken from the county's own tax-notice file.
- **Skip tracing input.** Owner name plus mailing address plus property address
  is exactly what a skip trace provider needs as its starting record.
- **Absentee & non-homestead targeting.** Exclude homestead-exempt parcels to
  drop owner-occupied primary residences.
- **Long-held property.** Filter for parcels whose last recorded sale predates
  any year you choose.
- **Companies vs. people.** Owner names are classified as individual or entity
  (LLC, corp, trust), so you can target either.
- **Market research and comps.** Values, land and building split, living area,
  year built, lot size and sale history, wherever the county records them.

## Output

One row per parcel:

```json
{
  "parcelId": "0000190060",
  "county": "Hillsborough County (Tampa)",
  "state": "FL",
  "ownerName": "JANE CECILIA MAGYAR TRUSTEE",
  "ownerType": "entity",
  "propertyAddress": "6908 JONES RD",
  "propertyCity": "ODESSA",
  "propertyZip": "33556",
  "mailingAddress": "12103 SAN CHALIFORD CT",
  "mailingCity": "TAMPA",
  "mailingState": "FL",
  "mailingZip": "33626",
  "isAbsenteeOwner": true,
  "isOutOfState": false,
  "hasHomesteadExemption": null,
  "justValue": 263429,
  "assessedValue": 263429,
  "taxableValue": 263429,
  "landValue": 96800,
  "buildingValue": 158629,
  "lastSaleDate": "1976-01-01",
  "lastSalePrice": 3800,
  "appreciationSinceSalePct": 98.6,
  "beds": 3,
  "baths": 2,
  "livingAreaSqFt": 1310,
  "yearBuilt": 1976,
  "propertyType": "Single Family",
  "landUseCode": "0100",
  "landUseDescription": "SINGLE FAMILY",
  "legalDescription": "..."
}
```

Export as JSON, CSV, Excel or XML, or pull it straight from the API.

## Filters

| Filter | What it does |
| --- | --- |
| Counties | Hillsborough, Pasco, or both |
| Property type | Single family, condo, multi-family, mobile home, vacant land, commercial, industrial, agricultural, institutional, government — normalised so it means the same thing in every county |
| Absentee owners only | Owner mailing address differs from the property address |
| Out-of-state owners only | Owner receives mail outside Florida |
| Exclude homestead | Drop owner-occupied primary residences |
| Owner type | Individuals only, companies/trusts only, or both |
| Cities / ZIP codes | Narrow to any part of either county |
| Market value | Minimum and maximum assessor just value |
| Year built | Built after / built before |
| Living area | Minimum square footage |
| Last sold before / after | Long-held property, or recent transfers |
| Owner name contains | Substring match, e.g. `HOLDINGS` |

## Example: absentee single-family homes, $150k–$400k, both counties

```json
{
  "counties": ["Hillsborough", "Pasco"],
  "propertyTypes": ["Single Family"],
  "absenteeOwnersOnly": true,
  "minJustValue": 150000,
  "maxJustValue": 400000,
  "maxResults": 5000
}
```

On a recent run that filter matched roughly 24,000 parcels in Hillsborough and
23,000 in Pasco.

## How fresh is it

Each county republishes its full roll on its own cycle — Hillsborough daily,
Pasco every few days. Every run downloads the current file and reads it end to
end, so you get what the assessor has now, not a cached copy from a broker.

Runtime is roughly **1–2 minutes for Hillsborough** and **4–5 minutes for
Pasco** (its file is a large spreadsheet rather than a database export). Give
the run a timeout of at least 600 seconds if you select both. Memory stays flat
regardless of how many parcels you pull, because both files are streamed.

## Notes and limits — please read

- **`appreciationSinceSalePct` is not equity.** It is the change in assessor
  value since the last recorded sale. Public rolls do not contain mortgage
  balances, so no dataset built from them can tell you real equity. Treat a
  high number as "there may be room here", not as a payoff figure.
- **No phone numbers or email addresses.** County tax rolls do not carry them.
  Owner name and mailing address are what the public record provides. Use a
  skip trace service if you need contact numbers.
- **Sale price is often $0 or nominal.** Quit claims, family transfers and
  foreclosure deeds are routinely recorded at $0 or $100. Where there is no
  usable sale price, `appreciationSinceSalePct` is `null` rather than an
  invented number.
- **Field coverage differs by county.** Hillsborough publishes bedroom and
  bathroom counts; Pasco does not, so those come back `null`. Pasco publishes a
  homestead-exemption flag and a pool flag; Hillsborough does not. Nothing is
  guessed to fill a gap.
  Land area is recorded in acres by Hillsborough and in square feet by Pasco,
  so `acreage` and `lotSizeSqFt` are both filled by exact conversion (43,560 sq
  ft per acre): converted, not estimated.
- **Two counties, not the whole state.** Every Florida county publishes in a
  different format. More counties are being added.

## Data sources

- Hillsborough County Property Appraiser — <https://downloads.hcpafl.org/>
- Pasco County Property Appraiser — <https://downloads.pascopa.com/>

Florida property tax rolls are public record under Florida's public records
law. This actor reads each county's own published bulk file. It does not bypass
authentication and does not scrape any login-gated system.

You are responsible for how you use the data, including compliance with
marketing rules such as TCPA and CAN-SPAM if you contact owners.
