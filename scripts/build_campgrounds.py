#!/usr/bin/env python3
"""Generate docs/data/campgrounds.json for the web app.

Enumerates recreation.gov campgrounds by tiling geographic searches across the
US and keeping only real overnight campgrounds (those with a campsite count),
which filters out the tickets/tours/permits/day-use entries that the search
endpoint otherwise mixes in. Keyless — uses the same public search API the CLI
uses, so the scheduled rebuild needs no API-key secret.

Run:  python scripts/build_campgrounds.py
Output: docs/data/campgrounds.json  ({ generated, count, campgrounds: [...] })
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time

import requests

_SEARCH = "https://www.recreation.gov/api/search"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
_RADIUS_MILES = 200
_PAGE_SIZE = 500
_DELAY = 0.3

_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "data", "campgrounds.json",
)


def _grid() -> list[tuple[float, float]]:
    """Overlapping tile centers covering the 50 states."""
    points: list[tuple[float, float]] = []
    lat = 25.0
    while lat <= 49.0:
        lng = -125.0
        while lng <= -66.0:
            points.append((round(lat, 2), round(lng, 2)))
            lng += 3.0
        lat += 2.5
    # Alaska and Hawaii
    points += [(61.2, -149.9), (64.8, -147.7), (58.3, -134.4), (55.3, -131.6)]
    points += [(20.8, -156.3), (21.4, -157.9), (19.6, -155.5)]
    return points


def _fetch_tile(lat: float, lng: float, session: requests.Session) -> list[dict]:
    params = {
        "lat": lat, "lng": lng, "radius": _RADIUS_MILES,
        "entity_type": "campground", "size": _PAGE_SIZE, "start": 0,
    }
    resp = session.get(_SEARCH, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json().get("results", []) or []


def build() -> dict:
    session = requests.Session()
    session.headers.update(_HEADERS)
    grid = _grid()
    found: dict[str, dict] = {}

    for i, (lat, lng) in enumerate(grid, 1):
        try:
            results = _fetch_tile(lat, lng, session)
        except requests.RequestException as exc:
            print(f"  tile {i}/{len(grid)} ({lat},{lng}) failed: {exc}")
            continue

        kept = 0
        for x in results:
            sites = x.get("campsites_count")
            if not sites:  # skip tickets/tours/permits/day-use (no campsites)
                continue
            eid = str(x.get("entity_id"))
            lat_v, lng_v = x.get("latitude"), x.get("longitude")
            if eid in found or lat_v is None or lng_v is None:
                continue
            found[eid] = {
                "id": eid,
                "name": (x.get("name") or "").strip(),
                "lat": round(float(lat_v), 5),
                "lng": round(float(lng_v), 5),
                "sites": int(sites),
                "reservable": bool(x.get("reservable")),
                "parent": (x.get("parent_name") or "").strip(),
            }
            kept += 1
        print(f"  tile {i}/{len(grid)} ({lat:>5},{lng:>7})  +{kept:<4} total {len(found)}")
        time.sleep(_DELAY)

    campgrounds = sorted(found.values(), key=lambda c: c["name"].lower())
    return {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "recreation.gov search API (geographic tiling)",
        "count": len(campgrounds),
        "campgrounds": campgrounds,
    }


def main() -> int:
    print("Building campground index from recreation.gov ...")
    data = build()
    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    with open(_OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    kb = os.path.getsize(_OUT) / 1024
    print(f"\nWrote {data['count']} campgrounds to {_OUT} ({kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
