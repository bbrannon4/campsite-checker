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
    """One bookable site on one night."""

    campground: Campground
    night: dt.date          # check-in date (the night you'd be staying)
    site_label: str
    site_id: str
    loop: str
    site_type: str
    max_length: int
    campsite_url: str


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


def target_nights(weeks: int, weekends_only: bool, today: dt.date | None = None) -> list[dt.date]:
    """Every check-in night to examine, from today through `weeks` weeks out.

    weekends-only keeps Friday and Saturday check-ins (i.e. Fri->Sat and
    Sat->Sun nights), which is what "weekend stays" means for a nightly system.
    """
    today = today or dt.date.today()
    end = today + dt.timedelta(weeks=weeks)
    nights: list[dt.date] = []
    day = today
    while day < end:
        if not weekends_only or day.weekday() in (4, 5):  # Fri=4, Sat=5
            nights.append(day)
        day += dt.timedelta(days=1)
    return nights


def _months_for(nights: list[dt.date]) -> list[tuple[int, int]]:
    seen = {(n.year, n.month) for n in nights}
    return sorted(seen)


def check_campground(
    provider: Provider,
    campground: Campground,
    nights: list[dt.date],
) -> CampgroundResult:
    """Fetch the months this campground needs, then collect open sites."""
    result = CampgroundResult(
        campground=campground,
        campground_url=provider.campground_url(campground.facility_id),
    )

    try:
        months = {
            (y, m): provider.get_month(campground.facility_id, y, m)
            for (y, m) in _months_for(nights)
        }
    except ProviderError as exc:
        result.error = str(exc)
        return result

    for night in nights:
        month = months.get((night.year, night.month))
        if month is None:
            continue
        for site_id, site in month.sites.items():
            if month.status(site_id, night) != STATUS_AVAILABLE:
                continue
            if campground.max_length and site.max_length and site.max_length < campground.max_length:
                continue
            result.open_sites.append(
                OpenSite(
                    campground=campground,
                    night=night,
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
    nights: list[dt.date],
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
        results.append(check_campground(provider, cg, nights))

    return results
