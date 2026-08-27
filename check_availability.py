#!/usr/bin/env python3
"""Check campsite availability on recreation.gov against a standing CSV list.

    python check_availability.py --weeks 4 --weekends-only

Read-only. No login or API key. See README.md for details.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from availability import CampgroundResult, check_all, target_nights
from campgrounds import load_campgrounds

_DEFAULT_CSV = "campsites.csv"
_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Check recreation.gov campsite availability from a CSV list.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--weeks", type=int, default=4,
                   help="how many weeks into the future to check (from today)")
    p.add_argument("--weekends-only", action="store_true",
                   help="only check Fri and Sat check-in nights")
    p.add_argument("--sites", default=_DEFAULT_CSV,
                   help="path to the campground CSV")
    p.add_argument("--delay", type=float, default=1.0,
                   help="seconds to wait between network requests")
    return p.parse_args(argv)


def format_results(results: list[CampgroundResult], nights: list[dt.date]) -> str:
    lines: list[str] = []
    span = ""
    if nights:
        span = f"  ({nights[0].isoformat()} -> {nights[-1].isoformat()}, {len(nights)} nights)"
    lines.append(f"Checked {len(results)} campground(s){span}\n")

    total_open = 0
    for res in results:
        cg = res.campground
        header = f"=== {cg.name}  [id {cg.facility_id}]"
        if cg.notes:
            header += f"  — {cg.notes}"
        lines.append(header)

        if res.error:
            lines.append(f"    ! could not check: {res.error}\n")
            continue

        if not res.open_sites:
            lines.append("    no availability in window")
            lines.append(f"    {res.campground_url}\n")
            continue

        # Group open sites by night for readable output.
        by_night: dict[dt.date, list] = {}
        for site in res.open_sites:
            by_night.setdefault(site.night, []).append(site)

        for night in sorted(by_night):
            sites = by_night[night]
            total_open += len(sites)
            checkout = night + dt.timedelta(days=1)
            lines.append(
                f"    {_DOW[night.weekday()]} {night.isoformat()} "
                f"-> {checkout.isoformat()}  ({len(sites)} site(s) open):"
            )
            for s in sites:
                bits = [f"#{s.site_label}"]
                if s.loop:
                    bits.append(f"loop {s.loop}")
                if s.site_type:
                    bits.append(s.site_type.lower())
                if s.max_length:
                    bits.append(f"{s.max_length}ft")
                lines.append(f"        {'  '.join(bits)}")
                lines.append(f"        book: {s.campsite_url}")
        lines.append(f"    campground: {res.campground_url}\n")

    lines.append(f"Total open site-nights found: {total_open}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        campgrounds = load_campgrounds(args.sites)
    except FileNotFoundError:
        print(f"error: CSV not found: {args.sites}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not campgrounds:
        print(f"no campgrounds found in {args.sites}", file=sys.stderr)
        return 1

    nights = target_nights(weeks=args.weeks, weekends_only=args.weekends_only)
    if not nights:
        print("no nights to check (try a larger --weeks)", file=sys.stderr)
        return 1

    results = check_all(campgrounds, nights, delay_seconds=args.delay)
    print(format_results(results, nights))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
