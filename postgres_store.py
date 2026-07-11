"""PostgreSQL clean store for normalized incidents.

This module owns all interaction with the serving-layer database and the dbt
target. It mirrors mongo_store: connection details come from environment
variables, connecting fails loudly if the database is unreachable, and the schema
is ensured on connect so the pipeline is reproducible from an empty database.

The relational model is three tables: ``beats`` (one row per police-beat page),
``incidents`` (one row per incident, keyed by the same raw_text_hash used for
dedup in the raw store), and ``incident_dates`` (a bridge table holding every
candidate date for multi-day beats). Writes are idempotent upserts so the
normalization job can be re-run safely.
"""

from __future__ import annotations

import logging
import os

import psycopg2
from psycopg2.extensions import connection as Connection

from normalizer.core import NormalizedIncident

DEFAULT_HOST = "localhost"
DEFAULT_PORT = "5432"
DEFAULT_DB = "byu_police_beat"
DEFAULT_USER = "postgres"
DEFAULT_PASSWORD = "postgres"

CONNECT_TIMEOUT_SECONDS = 5

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS beats (
    beat_url        TEXT PRIMARY KEY,
    beat_title      TEXT,
    published_at    TEXT,
    date_range_raw  TEXT,
    scraped_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS incidents (
    raw_text_hash       TEXT PRIMARY KEY,
    beat_url            TEXT REFERENCES beats(beat_url),
    incident_type       TEXT,
    incident_text       TEXT,
    location_zone       TEXT,
    location_confidence TEXT,
    location_source     TEXT,
    is_multi_date_beat  BOOLEAN NOT NULL DEFAULT FALSE,
    earliest_date       DATE,
    latest_date         DATE
);

CREATE TABLE IF NOT EXISTS incident_dates (
    raw_text_hash   TEXT REFERENCES incidents(raw_text_hash) ON DELETE CASCADE,
    incident_date   DATE NOT NULL,
    PRIMARY KEY (raw_text_hash, incident_date)
);

CREATE INDEX IF NOT EXISTS ix_incidents_zone ON incidents(location_zone);
CREATE INDEX IF NOT EXISTS ix_incidents_earliest_date ON incidents(earliest_date);
"""

_UPSERT_BEAT = """
INSERT INTO beats (beat_url, beat_title, published_at, date_range_raw, scraped_at)
VALUES (%(beat_url)s, %(beat_title)s, %(published_at)s, %(date_range_raw)s, %(scraped_at)s)
ON CONFLICT (beat_url) DO UPDATE SET
    beat_title = EXCLUDED.beat_title,
    published_at = EXCLUDED.published_at,
    date_range_raw = EXCLUDED.date_range_raw,
    scraped_at = EXCLUDED.scraped_at;
"""

_UPSERT_INCIDENT = """
INSERT INTO incidents (
    raw_text_hash, beat_url, incident_type, incident_text,
    location_zone, location_confidence, location_source,
    is_multi_date_beat, earliest_date, latest_date
) VALUES (
    %(raw_text_hash)s, %(beat_url)s, %(incident_type)s, %(incident_text)s,
    %(location_zone)s, %(location_confidence)s, %(location_source)s,
    %(is_multi_date_beat)s, %(earliest_date)s, %(latest_date)s
)
ON CONFLICT (raw_text_hash) DO UPDATE SET
    beat_url = EXCLUDED.beat_url,
    incident_type = EXCLUDED.incident_type,
    incident_text = EXCLUDED.incident_text,
    location_zone = EXCLUDED.location_zone,
    location_confidence = EXCLUDED.location_confidence,
    location_source = EXCLUDED.location_source,
    is_multi_date_beat = EXCLUDED.is_multi_date_beat,
    earliest_date = EXCLUDED.earliest_date,
    latest_date = EXCLUDED.latest_date;
"""


def connect() -> Connection:
    """Open a connection to PostgreSQL and ensure the schema exists.

    Connection details come from the POSTGRES_* environment variables (see
    .env.example). Raises SystemExit with a clear message if the database cannot
    be reached, so the pipeline fails loudly rather than hanging.
    """
    params = {
        "host": os.environ.get("POSTGRES_HOST", DEFAULT_HOST),
        "port": os.environ.get("POSTGRES_PORT", DEFAULT_PORT),
        "dbname": os.environ.get("POSTGRES_DB", DEFAULT_DB),
        "user": os.environ.get("POSTGRES_USER", DEFAULT_USER),
        "password": os.environ.get("POSTGRES_PASSWORD", DEFAULT_PASSWORD),
    }
    try:
        conn = psycopg2.connect(connect_timeout=CONNECT_TIMEOUT_SECONDS, **params)
    except psycopg2.OperationalError as exc:
        raise SystemExit(
            f"Could not connect to PostgreSQL at {params['host']}:{params['port']}. "
            f"Is the postgres container running? Original error: {exc}"
        ) from exc

    ensure_schema(conn)
    logging.info("Connected to PostgreSQL %s/%s", params["host"], params["dbname"])
    return conn


def ensure_schema(conn: Connection) -> None:
    """Create the beats/incidents/incident_dates tables and indexes if absent."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA_DDL)
    conn.commit()


def write_incident(conn: Connection, normalized: NormalizedIncident) -> None:
    """Upsert one normalized incident (beat, incident, and its dates) atomically.

    The date bridge rows are replaced wholesale rather than merged, so a re-run
    that changes a beat's parsed span cannot leave stale dates behind. Commits on
    success; rolls back and re-raises on failure so a partial write is never left.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(_UPSERT_BEAT, normalized.beat)
            cur.execute(_UPSERT_INCIDENT, normalized.incident)
            raw_text_hash = normalized.incident["raw_text_hash"]
            cur.execute(
                "DELETE FROM incident_dates WHERE raw_text_hash = %s", (raw_text_hash,)
            )
            cur.executemany(
                "INSERT INTO incident_dates (raw_text_hash, incident_date) VALUES (%s, %s)",
                [(raw_text_hash, day) for day in normalized.dates],
            )
        conn.commit()
    except psycopg2.Error:
        conn.rollback()
        raise
