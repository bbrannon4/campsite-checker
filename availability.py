"""Query logic: turn (campgrounds + date window) into open-site results.

This layer is deliberately separate from both the provider (which only fetches
raw month data) and the CLI/rendering (which only formats results). A future
"book this site" action would consume the same OpenSite results without any of
this needing to change.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from campgrounds import Campground
from providers import (
    Provider,
    ProviderError,
    STATUS_AVAILABLE,
    get_provider,
)


@dataclass(frozen=True)
class OpenSite:
    """One bookable site available for a full stay starting on `night`."""

    campground: Campground
    night: dt.date          # check-in date (first night of the stay)
    stay_length: int        # number of consecutive nights this site is open for
    site_label: str
    site_id: str
    loop: str
    site_type: str
    max_length: int
    campsite_url: str

    @property
    def checkout(self) -> dt.date:
        return self.night + dt.timedelta(days=self.stay_length)


@dataclass
class CampgroundResult:
    """Everything found (or the error) for a single campground."""

    campground: Campground
    campground_url: str = ""
    open_sites: list[OpenSite] = None  # type: ignore[assignment]
    error: str = ""

    def __post_init__(self):
        if self.open_sites is None:
            self.open_sites = []


_WEEKEND_NIGHTS = (4, 5)  # a "weekend night" is a Friday or Saturday night


def target_checkins(
    weeks: int,
    weekends_only: bool,
    stay_length: int,
    today: dt.date | None = None,
) -> list[dt.date]:
    """Check-in dates to examine, from today through `weeks` weeks out.

    A stay is a run of `stay_length` consecutive nights beginning on the
    check-in date. With weekends_only, a check-in qualifies only if *every*
    night of the stay is a Friday or Saturday night. So a 2-night weekend stay
    is Friday check-in (Fri+Sat); a 1-night weekend stay is Friday or Saturday.
    (A 3-night all-weekend stay is impossible and yields nothing.)
    """
    today = today or dt.date.today()
    end = today + dt.timedelta(weeks=weeks)
    checkins: list[dt.date] = []
    day = today
    while day < end:
        stay = [day + dt.timedelta(days=i) for i in range(stay_length)]
        if not weekends_only or all(d.weekday() in _WEEKEND_NIGHTS for d in stay):
            checkins.append(day)
        day += dt.timedelta(days=1)
    return checkins


def _stay_dates(checkin: dt.date, stay_length: int) -> list[dt.date]:
    return [checkin + dt.timedelta(days=i) for i in range(stay_length)]


def _months_for(checkins: list[dt.date], stay_length: int) -> list[tuple[int, int]]:
    # A stay can spill into the next month, so cover every night of every stay.
    seen: set[tuple[int, int]] = set()
    for c in checkins:
        for d in _stay_dates(c, stay_length):
            seen.add((d.year, d.month))
    return sorted(seen)


def check_campground(
    provider: Provider,
    campground: Campground,
    checkins: list[dt.date],
    stay_length: int = 1,
) -> CampgroundResult:
    """Fetch the months this campground needs, then collect sites open for the
    full `stay_length`-night stay beginning on each check-in date."""
    result = CampgroundResult(
        campground=campground,
        campground_url=provider.campground_url(campground.facility_id),
    )

    try:
        months = {
            (y, m): provider.get_month(campground.facility_id, y, m)
            for (y, m) in _months_for(checkins, stay_length)
        }
    except ProviderError as exc:
        result.error = str(exc)
        return result

    def available_on(site_id: str, day: dt.date) -> bool:
        # Only STATUS_AVAILABLE counts: online-reservable AND open. First-come-
        # first-serve nights never carry this status, so they are excluded here.
        month = months.get((day.year, day.month))
        return month is not None and month.status(site_id, day) == STATUS_AVAILABLE

    for checkin in checkins:
        stay = _stay_dates(checkin, stay_length)
        checkin_month = months.get((checkin.year, checkin.month))
        if checkin_month is None:
            continue
        for site_id, site in checkin_month.sites.items():
            if not site.is_overnight:
                continue
            if campground.max_length and site.max_length and site.max_length < campground.max_length:
                continue
            # The same site must be open every night of the stay.
            if not all(available_on(site_id, d) for d in stay):
                continue
            result.open_sites.append(
                OpenSite(
                    campground=campground,
                    night=checkin,
                    stay_length=stay_length,
                    site_label=site.label,
                    site_id=site_id,
                    loop=site.loop,
                    site_type=site.site_type,
                    max_length=site.max_length,
                    campsite_url=provider.campsite_url(site_id),
                )
            )

    result.open_sites.sort(key=lambda s: (s.night, s.site_label))
    return result


def check_all(
    campgrounds: list[Campground],
    checkins: list[dt.date],
    stay_length: int = 1,
    delay_seconds: float = 1.0,
) -> list[CampgroundResult]:
    """Check every campground, reusing one provider instance per provider key
    so month caching and rate-limiting apply across the whole run."""
    provider_cache: dict[str, Provider] = {}
    results: list[CampgroundResult] = []

    for cg in campgrounds:
        try:
            provider = provider_cache.get(cg.provider)
            if provider is None:
                provider = get_provider(cg.provider, delay_seconds=delay_seconds)
                provider_cache[cg.provider] = provider
        except ProviderError as exc:
            results.append(CampgroundResult(campground=cg, error=str(exc)))
            continue
        results.append(check_campground(provider, cg, checkins, stay_length))

    return results
