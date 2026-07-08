"""Pure transform from a raw Mongo incident document to relational rows.

Kept free of any database access so it can be unit-tested in isolation. The
transform splits one denormalized document into the three entities of the clean
model: the beat it came from, the incident itself, and its candidate dates.

A beat that spans several days doesn't say which day an incident happened, so all
candidate dates are preserved in the bridge table and the incident carries the
span endpoints (earliest_date / latest_date) for convenient single-date queries.
ISO date strings (YYYY-MM-DD) sort chronologically, so min/max over them is safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedIncident:
    """One raw document reshaped into rows for the beats/incidents/dates tables."""

    beat: dict[str, Any]
    incident: dict[str, Any]
    dates: list[str]


def transform(document: dict[str, Any]) -> NormalizedIncident:
    """Reshape a raw Mongo incident document into relational rows."""
    dates = [d for d in document.get("incident_dates", []) if d]

    beat = {
        "beat_url": document.get("beat_url"),
        "beat_title": document.get("beat_title"),
        "published_at": document.get("beat_published_at") or None,
        "date_range_raw": document.get("date_range_raw"),
        "scraped_at": document.get("scraped_at"),
    }

    incident = {
        "raw_text_hash": document.get("raw_text_hash"),
        "beat_url": document.get("beat_url"),
        "incident_type": document.get("incident_type"),
        "incident_text": document.get("incident_text"),
        "location_zone": document.get("location_zone"),
        "location_confidence": document.get("location_confidence"),
        "location_source": document.get("location_source"),
        "is_multi_date_beat": bool(document.get("is_multi_date_beat", False)),
        "earliest_date": min(dates) if dates else None,
        "latest_date": max(dates) if dates else None,
    }

    return NormalizedIncident(beat=beat, incident=incident, dates=dates)
