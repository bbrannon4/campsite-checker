"""Provider registry.

CSV rows name a provider by its short key (default: recreation_gov). The CLI
resolves that key to a Provider instance through `get_provider`, so adding a new
backend later is: write the class, register it here. Nothing else changes.
"""

from __future__ import annotations

from .base import (
    MonthAvailability,
    Provider,
    ProviderError,
    Site,
    STATUS_AVAILABLE,
    STATUS_BOOKED,
    STATUS_UNAVAILABLE,
)
from .recreation_gov import RecreationGovProvider

DEFAULT_PROVIDER = "recreation_gov"

# Factories, not instances, so each provider is built once with runtime config
# (e.g. the request delay) and reused across all campgrounds that use it.
_REGISTRY = {
    "recreation_gov": RecreationGovProvider,
}


def get_provider(name: str, **kwargs) -> Provider:
    key = (name or DEFAULT_PROVIDER).strip()
    try:
        factory = _REGISTRY[key]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise ProviderError(f"unknown provider '{name}'. known: {known}") from None
    return factory(**kwargs)


def known_providers() -> list[str]:
    return sorted(_REGISTRY)


__all__ = [
    "get_provider",
    "known_providers",
    "Provider",
    "ProviderError",
    "MonthAvailability",
    "Site",
    "STATUS_AVAILABLE",
    "STATUS_BOOKED",
    "STATUS_UNAVAILABLE",
    "DEFAULT_PROVIDER",
]
