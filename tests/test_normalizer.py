"""Unit tests for the pure Mongo-document -> relational transform."""

from __future__ import annotations

from normalizer.core import transform

_MULTI_DATE_DOC = {
    "beat_url": "https://police.byu.edu/beat/1",
    "beat_title": "Police Beat - 06/01/2026 - 06/03/2026",
    "beat_published_at": "2026-06-04",
    "date_range_raw": "06/01/2026 - 06/03/2026",
    "incident_dates": ["2026-06-01", "2026-06-02", "2026-06-03"],
    "is_multi_date_beat": True,
    "incident_type": "Theft",
    "incident_text": "A bike was reported stolen from the HBLL racks.",
    "raw_text_hash": "abc123",
    "scraped_at": "2026-06-04T12:00:00+00:00",
    "location_zone": "ACADEMIC_CORE",
    "location_confidence": "HIGH",
    "location_source": "landmark",
}


def test_splits_into_beat_incident_and_dates():
    result = transform(_MULTI_DATE_DOC)
    assert result.beat["beat_url"] == "https://police.byu.edu/beat/1"
    assert result.beat["published_at"] == "2026-06-04"
    assert result.incident["raw_text_hash"] == "abc123"
    assert result.incident["location_zone"] == "ACADEMIC_CORE"
    assert result.dates == ["2026-06-01", "2026-06-02", "2026-06-03"]


def test_span_endpoints_from_candidate_dates():
    result = transform(_MULTI_DATE_DOC)
    assert result.incident["earliest_date"] == "2026-06-01"
    assert result.incident["latest_date"] == "2026-06-03"
    assert result.incident["is_multi_date_beat"] is True


def test_single_date_incident():
    doc = dict(_MULTI_DATE_DOC, incident_dates=["2026-06-01"], is_multi_date_beat=False)
    result = transform(doc)
    assert result.incident["earliest_date"] == result.incident["latest_date"] == "2026-06-01"
    assert result.dates == ["2026-06-01"]


def test_missing_dates_yield_null_endpoints():
    doc = dict(_MULTI_DATE_DOC, incident_dates=[])
    result = transform(doc)
    assert result.incident["earliest_date"] is None
    assert result.incident["latest_date"] is None
    assert result.dates == []


def test_blank_dates_are_dropped():
    doc = dict(_MULTI_DATE_DOC, incident_dates=["2026-06-01", "", None])
    result = transform(doc)
    assert result.dates == ["2026-06-01"]
