"""Venue profiles: loading and listing the YAML files in references/venues/."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

VENUES = Path(__file__).resolve().parents[2] / "references" / "venues"
MAX_AGE_DAYS = 180


def list_venues() -> list:
    import yaml

    out = []
    for path in sorted(VENUES.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        out.append({"id": data["id"], "name": data["name"], "group": data["group"],
                    "checked_on": data["checked_on"]})
    return out


def load_venue(venue_id: Optional[str]) -> Optional[dict]:
    if not venue_id:
        return None
    import yaml

    path = VENUES / f"{venue_id}.yaml"
    if not path.exists():
        raise SystemExit(f"Unknown venue '{venue_id}'. Run `pc.py venues` to list them.")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    age = (dt.date.today() - dt.date.fromisoformat(data["checked_on"])).days
    data["_stale"] = age > MAX_AGE_DAYS
    data["_age_days"] = age
    return data


def rule(venue: Optional[dict], key: str, confirmed_only: bool = False) -> Optional[dict]:
    """Return a venue rule dict, or None. Unconfirmed rules are returned unless confirmed_only."""
    if not venue:
        return None
    r = venue.get("rules", {}).get(key)
    if not r or r.get("status") == "not_stated":
        return None
    if confirmed_only and r.get("status") != "confirmed":
        return None
    return r
