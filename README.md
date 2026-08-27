# campsite-checker

A small, local Python CLI that checks campsite availability on **recreation.gov**
against a standing list of campgrounds you maintain by hand. Read-only — it uses
the public, unauthenticated availability API (the same endpoint `camply` and
`rgov` use). No login, no API key, no booking.

## Setup

```bash
cd campsite-checker
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

A bare run checks the **next two weeks** for a **two-night weekend stay**:

```bash
python check_availability.py
```

Output is a matrix — one row per campground, one column per check-in date,
each cell the number of reservable sites open for the *whole* stay (blank =
none). First-come-first-serve and day-use sites are never counted.

```
Reservable availability, 2-night stay (first-come-first-serve excluded) — 2026-08-28 → 2026-10-04
Columns = check-in date. Cells = # of sites open for the whole stay; blank = none.

Campground   Fri 8/28  Fri 9/04  Fri 9/11  Fri 9/18  Fri 9/25  Fri 10/02
------------------------------------------------------------------------
Arapaho Bay                             6        10
```

Add `--detail` to also list each open site with a direct booking link.

Options:

| flag | meaning | default |
| --- | --- | --- |
| `--weeks N` | how many weeks ahead to check, from today | `2` |
| `--nights N` | length of stay — consecutive nights the *same* site must be open | `2` |
| `--weekends-only` / `--no-weekends-only` | restrict to weekend stays (see below) | on |
| `--detail` | also print each open site + booking link | off |
| `--sites PATH` | path to the campground CSV | `campsites.csv` |
| `--delay SECONDS` | pause between network requests (be polite) | `1.0` |

**Length of stay matters.** A cell counts only sites open for *every* night of
the stay, so "site A open Fri, site B open Sat" is not the same as "one site
open both nights" — only the latter counts for `--nights 2`.

**What "weekend" means.** A weekend night is a Friday or Saturday night, and a
weekend stay is one where *every* night is a weekend night. So a 2-night weekend
stay is a **Friday check-in** (Fri+Sat); a 1-night weekend stay is Friday *or*
Saturday. (A 3-plus-night all-weekend stay can't fit inside Fri/Sat and returns
nothing — use `--no-weekends-only` for longer trips.)

Examples:

```bash
python check_availability.py --weeks 4                 # 4 wks, 2-night weekends
python check_availability.py --nights 1                # single weekend nights
python check_availability.py --nights 3 --no-weekends-only   # any 3-night stay
```

## The campground list (`campsites.csv`)

Plain CSV you edit in any text editor. Header row required; extra columns are
ignored so you can annotate freely.

| column | required | meaning |
| --- | --- | --- |
| `name` | yes | your label, e.g. `West Lake` |
| `facility_id` | yes | the recreation.gov campground id, e.g. `231855` |
| `provider` | no | backend key; blank = `recreation_gov` |
| `notes` | no | free text, e.g. `near Red Feather Lakes` |
| `max_length` | no | your rig length in feet; sites shorter than this are hidden (popup camper: leave `0`) |

Finding a `facility_id`: open the campground on recreation.gov — the number in
the URL `recreation.gov/camping/campgrounds/<ID>` is it.

## How it works / how it's built

Three separate layers, so each can grow independently:

- **`providers/`** — pluggable reservation backends. `base.py` defines the
  `Provider` interface and provider-agnostic types (`Site`, `MonthAvailability`);
  `recreation_gov.py` implements it against recreation.gov's month endpoint and
  maps its status vocabulary onto normalized statuses. Fetched months are cached
  and requests are spaced out.
- **`availability.py`** — query logic: given campgrounds + a window of nights,
  returns `OpenSite` results. Knows nothing about HTTP or terminal formatting.
- **`check_availability.py`** — CLI + rendering only.

### Deliberately not built yet

- **Other providers.** Adding one (e.g. ReserveCalifornia) means writing a class
  in `providers/` and registering it in `providers/__init__.py` — nothing in the
  CLI or query layer hardcodes recreation.gov field names.
- **Booking.** This is availability-only. A future "book this site" action would
  consume the same `OpenSite` results and live behind a separate provider method,
  keeping read and write paths cleanly divided.
```
