"""Normalize classified incidents from the Mongo raw store into PostgreSQL.

The raw store holds one denormalized document per incident. This package reshapes
those documents into a clean relational model (beats, incidents, and a bridge
table of candidate dates) suitable for the serving layer and the dbt project.
The transform in ``normalizer.core`` is pure and testable; ``normalizer.runner``
does the Mongo-read / Postgres-write orchestration.
"""

from __future__ import annotations

from normalizer.core import NormalizedIncident, transform

__all__ = ["NormalizedIncident", "transform"]
