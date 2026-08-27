"""Load the hand-maintained campground list from CSV.

CSV columns (header row required):
    name          - your label, e.g. "West Lake"           (required)
    facility_id   - the provider's campground id            (required)
    provider      - provider key; blank = recreation_gov    (optional)
    notes         - free text                               (optional)
    max_length    - your rig length in feet, for filtering  (optional)

Extra columns are ignored, so you can annotate freely. Blank lines and rows
starting with '#' are skipped.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass

from providers import DEFAULT_PROVIDER


@dataclass(frozen=True)
class Campground:
    name: str
    facility_id: str
    provider: str = DEFAULT_PROVIDER
    notes: str = ""
    max_length: int = 0  # site must fit at least this length; 0 = no filter


def load_campgrounds(path: str) -> list[Campground]:
    out: list[Campground] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return out
        cols = {c.strip().lower(): c for c in reader.fieldnames}
        if "name" not in cols or "facility_id" not in cols:
            raise ValueError(
                f"{path} must have at least 'name' and 'facility_id' columns; "
                f"found: {reader.fieldnames}"
            )

        for row in reader:
            name = (row.get(cols["name"]) or "").strip()
            facility_id = (row.get(cols["facility_id"]) or "").strip()
            if not name or name.startswith("#") or not facility_id:
                continue
            out.append(
                Campground(
                    name=name,
                    facility_id=facility_id,
                    provider=(_get(row, cols, "provider") or DEFAULT_PROVIDER).strip(),
                    notes=_get(row, cols, "notes").strip(),
                    max_length=_to_int(_get(row, cols, "max_length")),
                )
            )
    return out


def _get(row: dict, cols: dict, key: str) -> str:
    col = cols.get(key)
    if not col:
        return ""
    return row.get(col) or ""


def _to_int(val: str) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return 0
