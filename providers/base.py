"""Provider abstraction + normalized data types.

A "provider" is a reservation backend (recreation.gov today; ReserveCalifornia,
state-park systems, etc. later). The rest of the app talks only to this
interface and the normalized types below — it never sees a provider's raw JSON
or field names. That keeps the CLI/rendering layers provider-agnostic and makes
adding a second provider an additive change rather than a rewrite.
"""

from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass, field


# Normalized status for a single site on a single night. Each provider maps its
# own vocabulary ("Available", "Reserved", "NYR", ...) onto these.
STATUS_AVAILABLE = "available"
STATUS_BOOKED = "booked"
STATUS_UNAVAILABLE = "unavailable"  # closed, not reservable, not yet released


@dataclass(frozen=True)
class Site:
    """A single campsite within a campground, provider-agnostic."""

    site_id: str          # provider's internal id (used to build booking links)
    label: str            # human-facing site number/name, e.g. "A017"
    loop: str = ""        # loop/area name if the provider exposes one
    site_type: str = ""   # e.g. "STANDARD NONELECTRIC", "TENT ONLY"
    max_length: int = 0   # max RV/trailer length in feet, 0 if unknown/unlimited
    is_overnight: bool = True  # False for day-use sites, which we never count


@dataclass
class MonthAvailability:
    """Normalized availability for one campground for one calendar month.

    nights maps site_id -> { date -> status }, where status is one of the
    STATUS_* constants above. Only the provider knows how to populate this;
    everyone downstream reads it the same way regardless of provider.
    """

    facility_id: str
    year: int
    month: int
    sites: dict[str, Site] = field(default_factory=dict)
    nights: dict[str, dict[dt.date, str]] = field(default_factory=dict)

    def status(self, site_id: str, night: dt.date) -> str:
        return self.nights.get(site_id, {}).get(night, STATUS_UNAVAILABLE)


class Provider(abc.ABC):
    """Read-only availability provider.

    Deliberately scoped to *fetching availability* only. Booking/reservation
    actions are intentionally not part of this interface yet — when they come,
    they belong in a separate method (or a separate BookingProvider mixin) so
    that read and write paths stay cleanly divided.
    """

    #: short stable key used in the CSV `provider` column and the registry
    name: str = "base"

    @abc.abstractmethod
    def get_month(self, facility_id: str, year: int, month: int) -> MonthAvailability:
        """Return normalized availability for one campground for one month.

        Implementations should cache and reuse a fetched month rather than
        re-requesting it, and raise ProviderError on unrecoverable failures.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def campground_url(self, facility_id: str) -> str:
        """Direct booking/overview link for the campground."""
        raise NotImplementedError

    @abc.abstractmethod
    def campsite_url(self, site_id: str) -> str:
        """Direct booking link for a specific site."""
        raise NotImplementedError


class ProviderError(Exception):
    """Raised when a provider cannot return usable data (bad id, network, etc.)."""
