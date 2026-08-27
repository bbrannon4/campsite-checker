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

```bash
python check_availability.py --weeks 4 --weekends-only
```

Options:

| flag | meaning | default |
| --- | --- | --- |
| `--weeks N` | how many weeks ahead to check, from today | `4` |
| `--weekends-only` | only Friday & Saturday check-in nights | off |
| `--sites PATH` | path to the campground CSV | `campsites.csv` |
| `--delay SECONDS` | pause between network requests (be polite) | `1.0` |

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
