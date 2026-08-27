"""recreation.gov availability provider.

Uses the public, unauthenticated month-availability endpoint that camply/rgov
rely on:

    GET https://www.recreation.gov/api/camps/availability/campground/{id}/month
        ?start_date=YYYY-MM-01T00:00:00.000Z

No API key or login is required for read-only availability. A browser-like
User-Agent is required or the endpoint returns 403.
"""

from __future__ import annotations

import datetime as dt
import time

import requests

from .base import (
    MonthAvailability,
    Provider,
    ProviderError,
    Site,
    STATUS_AVAILABLE,
    STATUS_BOOKED,
    STATUS_UNAVAILABLE,
)

_API = "https://www.recreation.gov/api/camps/availability/campground/{facility_id}/month"
_WEB = "https://www.recreation.gov"

# recreation.gov's per-night availability vocabulary -> normalized status.
_STATUS_MAP = {
    "Available": STATUS_AVAILABLE,
    "Reserved": STATUS_BOOKED,
    "Not Available": STATUS_UNAVAILABLE,
    "Not Reservable": STATUS_UNAVAILABLE,
    "Not Reservable Management": STATUS_UNAVAILABLE,
    "Open": STATUS_UNAVAILABLE,      # walk-up/first-come, not bookable online
    "NYR": STATUS_UNAVAILABLE,       # not yet released
    "Lottery": STATUS_UNAVAILABLE,
}


class RecreationGovProvider(Provider):
    name = "recreation_gov"

    def __init__(self, delay_seconds: float = 1.0, timeout: float = 30.0):
        # delay between *network* fetches (cache hits don't sleep)
        self.delay_seconds = delay_seconds
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept": "application/json",
            }
        )
        # cache: (facility_id, year, month) -> MonthAvailability
        self._cache: dict[tuple[str, int, int], MonthAvailability] = {}
        self._made_request = False  # so we only sleep *between* real requests

    def get_month(self, facility_id: str, year: int, month: int) -> MonthAvailability:
        key = (str(facility_id), year, month)
        if key in self._cache:
            return self._cache[key]

        # Be polite: pause between consecutive network requests.
        if self._made_request and self.delay_seconds > 0:
            time.sleep(self.delay_seconds)

        start = dt.datetime(year, month, 1)
        params = {"start_date": start.strftime("%Y-%m-01T00:00:00.000Z")}
        url = _API.format(facility_id=facility_id)

        try:
            resp = self._session.get(url, params=params, timeout=self.timeout)
            self._made_request = True
        except requests.RequestException as exc:
            raise ProviderError(f"network error fetching {facility_id}: {exc}") from exc

        if resp.status_code == 404:
            raise ProviderError(f"campground {facility_id} not found (404)")
        if resp.status_code != 200:
            raise ProviderError(
                f"unexpected {resp.status_code} for {facility_id}: {resp.text[:200]}"
            )

        try:
            payload = resp.json()
        except ValueError as exc:
            raise ProviderError(f"non-JSON response for {facility_id}: {exc}") from exc

        result = self._parse(str(facility_id), year, month, payload)
        self._cache[key] = result
        return result

    def _parse(
        self, facility_id: str, year: int, month: int, payload: dict
    ) -> MonthAvailability:
        result = MonthAvailability(facility_id=facility_id, year=year, month=month)
        campsites = (payload or {}).get("campsites") or {}

        for site_id, raw in campsites.items():
            # recreation.gov exposes site length under a couple of keys; be lenient.
            max_len = _first_int(raw, ("max_length", "max_vehicle_length")) or 0

            result.sites[site_id] = Site(
                site_id=site_id,
                label=str(raw.get("site") or site_id),
                loop=str(raw.get("loop") or ""),
                site_type=str(raw.get("campsite_type") or ""),
                max_length=max_len,
            )

            nights: dict[dt.date, str] = {}
            for date_str, status in (raw.get("availabilities") or {}).items():
                night = _parse_date(date_str)
                if night is None:
                    continue
                nights[night] = _STATUS_MAP.get(status, STATUS_UNAVAILABLE)
            result.nights[site_id] = nights

        return result

    def campground_url(self, facility_id: str) -> str:
        return f"{_WEB}/camping/campgrounds/{facility_id}"

    def campsite_url(self, site_id: str) -> str:
        return f"{_WEB}/camping/campsites/{site_id}"


def _parse_date(date_str: str) -> dt.date | None:
    # e.g. "2026-08-01T00:00:00Z"
    try:
        return dt.datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _first_int(raw: dict, keys: tuple[str, ...]) -> int | None:
    for k in keys:
        val = raw.get(k)
        if val in (None, ""):
            continue
        try:
            return int(float(val))
        except (TypeError, ValueError):
            continue
    return None
