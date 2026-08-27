#!/usr/bin/env python3
"""Check campsite availability on recreation.gov against a standing CSV list.

    python check_availability.py --weeks 2

Weekends-only (Fri & Sat check-in nights) by default; pass --no-weekends-only
to check every night. Reservable sites only — first-come-first-serve and
day-use are excluded. Read-only; no login or API key. See README.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from availability import CampgroundResult, check_all, target_checkins
from campgrounds import load_campgrounds

_DEFAULT_CSV = "campsites.csv"
_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Check recreation.gov campsite availability from a CSV list.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--weeks", type=int, default=2,
                   help="how many weeks into the future to check (from today)")
    p.add_argument("--nights", type=int, default=2,
                   help="length of stay: consecutive nights the same site must "
                        "be open")
    p.add_argument("--weekends-only", action=argparse.BooleanOptionalAction,
                   default=True,
                   help="only stays whose every night is Fri/Sat (a 2-night "
                        "stay = Fri check-in; use --no-weekends-only for any night)")
    p.add_argument("--sites", default=_DEFAULT_CSV,
                   help="path to the campground CSV")
    p.add_argument("--delay", type=float, default=1.0,
                   help="seconds to wait between network requests")
    p.add_argument("--detail", action="store_true",
                   help="also print each open site with a direct booking link")
    return p.parse_args(argv)


def _col_header(night: dt.date) -> str:
    return f"{_DOW[night.weekday()]} {night.month}/{night.day:02d}"


def format_matrix(
    results: list[CampgroundResult], checkins: list[dt.date], stay_length: int
) -> str:
    """Rows = campgrounds, columns = check-in dates, cell = # of reservable
    sites open for the whole stay starting that date (blank for none)."""
    lines: list[str] = []
    span = ""
    if checkins:
        last_out = (checkins[-1] + dt.timedelta(days=stay_length)).isoformat()
        span = f"{checkins[0].isoformat()} → {last_out}"
    stay = f"{stay_length}-night stay" if stay_length != 1 else "1-night stay"
    lines.append(f"Reservable availability, {stay} (first-come-first-serve "
                 f"excluded) — {span}")
    lines.append("Columns = check-in date. Cells = # of sites open for the "
                 "whole stay; blank = none.\n")

    headers = [_col_header(n) for n in checkins]
    label_w = max([len("Campground")] + [len(r.campground.name) for r in results])
    col_w = [max(len(h), 3) for h in headers]

    # header row
    row = "Campground".ljust(label_w)
    for h, w in zip(headers, col_w):
        row += "  " + h.rjust(w)
    lines.append(row)
    lines.append("-" * len(row))

    errors: list[str] = []
    for res in results:
        name = res.campground.name
        if res.error:
            errors.append(f"{name}: {res.error}")
            row = name.ljust(label_w)
            for w in col_w:
                row += "  " + "err".rjust(w)
            lines.append(row)
            continue

        counts = {n: 0 for n in checkins}
        for site in res.open_sites:
            if site.night in counts:
                counts[site.night] += 1

        row = name.ljust(label_w)
        for n, w in zip(checkins, col_w):
            c = counts[n]
            row += "  " + (str(c) if c else "").rjust(w)
        lines.append(row)

    if errors:
        lines.append("")
        for e in errors:
            lines.append(f"  ! {e}")

    return "\n".join(lines)


def format_detail(results: list[CampgroundResult]) -> str:
    lines: list[str] = ["", "Open sites with booking links", "=" * 30]
    for res in results:
        cg = res.campground
        lines.append(f"\n{cg.name}  [id {cg.facility_id}]")
        if res.error:
            lines.append(f"    ! could not check: {res.error}")
            continue
        if not res.open_sites:
            lines.append(f"    no availability  ({res.campground_url})")
            continue
        by_night: dict[dt.date, list] = {}
        for s in res.open_sites:
            by_night.setdefault(s.night, []).append(s)
        for night in sorted(by_night):
            checkout = by_night[night][0].checkout
            lines.append(f"    {_DOW[night.weekday()]} {night.isoformat()} "
                         f"-> {checkout.isoformat()}:")
            for s in by_night[night]:
                bits = [f"#{s.site_label}"]
                if s.loop:
                    bits.append(f"loop {s.loop}")
                if s.site_type:
                    bits.append(s.site_type.lower())
                lines.append(f"        {'  '.join(bits)}  {s.campsite_url}")
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

    if args.nights < 1:
        print("error: --nights must be at least 1", file=sys.stderr)
        return 2

    checkins = target_checkins(
        weeks=args.weeks,
        weekends_only=args.weekends_only,
        stay_length=args.nights,
    )
    if not checkins:
        print("no check-in dates to check. A weekends-only stay longer than "
              "2 nights can't fit inside Fri/Sat — try --nights 2 or "
              "--no-weekends-only.", file=sys.stderr)
        return 1

    results = check_all(
        campgrounds, checkins, stay_length=args.nights, delay_seconds=args.delay
    )
    print(format_matrix(results, checkins, args.nights))
    if args.detail:
        print(format_detail(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
