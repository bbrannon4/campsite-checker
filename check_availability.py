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
    p.add_argument("--format", choices=("grid", "md", "csv"), default="grid",
                   help="table style: grid (box-drawing), md (markdown), or csv")
    p.add_argument("--detail", action="store_true",
                   help="also print each open site with a direct booking link")
    return p.parse_args(argv)


def _col_header(night: dt.date) -> str:
    return f"{_DOW[night.weekday()]} {night.month}/{night.day:02d}"


def _matrix_data(
    results: list[CampgroundResult], checkins: list[dt.date]
) -> tuple[list[str], list[list[str]], list[str]]:
    """Return (headers, rows, errors) as plain strings, format-agnostic.

    rows[i] = [campground name, cell, cell, ...] aligned to headers[1:].
    """
    headers = ["Campground"] + [_col_header(n) for n in checkins]
    rows: list[list[str]] = []
    errors: list[str] = []
    for res in results:
        name = res.campground.name
        if res.error:
            errors.append(f"{name}: {res.error}")
            rows.append([name] + ["err"] * len(checkins))
            continue
        counts = {n: 0 for n in checkins}
        for site in res.open_sites:
            if site.night in counts:
                counts[site.night] += 1
        rows.append([name] + [(str(counts[n]) if counts[n] else "") for n in checkins])
    return headers, rows, errors


def _title(checkins: list[dt.date], stay_length: int) -> str:
    span = ""
    if checkins:
        last_out = (checkins[-1] + dt.timedelta(days=stay_length)).isoformat()
        span = f"{checkins[0].isoformat()} → {last_out}"
    stay = f"{stay_length}-night stay" if stay_length != 1 else "1-night stay"
    return f"Reservable availability, {stay} (first-come-first-serve excluded) — {span}"


def _render_grid(headers: list[str], rows: list[list[str]]) -> str:
    """A box-drawing table. Column 0 left-aligned, count columns right-aligned."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def cell(text: str, i: int) -> str:
        return text.ljust(widths[i]) if i == 0 else text.rjust(widths[i])

    def border(left: str, mid: str, right: str) -> str:
        return left + mid.join("─" * (w + 2) for w in widths) + right

    def data_row(cells: list[str]) -> str:
        return "│ " + " │ ".join(cell(c, i) for i, c in enumerate(cells)) + " │"

    out = [border("┌", "┬", "┐"), data_row(headers), border("├", "┼", "┤")]
    out += [data_row(r) for r in rows]
    out.append(border("└", "┴", "┘"))
    return "\n".join(out)


def _render_md(headers: list[str], rows: list[list[str]]) -> str:
    def line(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    # left-align the name column, right-align the count columns
    sep = ["---"] + ["--:"] * (len(headers) - 1)
    out = [line(headers), line(sep)] + [line(r) for r in rows]
    return "\n".join(out)


def _render_csv(headers: list[str], rows: list[list[str]]) -> str:
    import csv as _csv
    import io

    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    return buf.getvalue().rstrip("\n")


_RENDERERS = {"grid": _render_grid, "md": _render_md, "csv": _render_csv}


def format_matrix(
    results: list[CampgroundResult],
    checkins: list[dt.date],
    stay_length: int,
    fmt: str = "grid",
) -> str:
    headers, rows, errors = _matrix_data(results, checkins)
    table = _RENDERERS[fmt](headers, rows)
    if fmt == "csv":  # keep csv output clean/importable
        return table

    parts = [
        _title(checkins, stay_length),
        "Columns = check-in date. Cells = # of sites open for the whole stay; "
        "blank = none.",
        "",
        table,
    ]
    if errors:
        parts.append("")
        parts += [f"  ! {e}" for e in errors]
    return "\n".join(parts)


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
    print(format_matrix(results, checkins, args.nights, fmt=args.format))
    if args.detail:
        print(format_detail(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
