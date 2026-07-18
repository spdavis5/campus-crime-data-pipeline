-- Synthetic source data for CI so dbt can build and run its tests without the
-- full scrape -> classify -> normalize pipeline. Mirrors the schema created by
-- postgres_store.SCHEMA_DDL (public.beats / incidents / incident_dates) and
-- inserts a handful of internally-consistent rows. Dates sit inside the seeded
-- academic calendar so dim_date's finals/break/semester joins exercise real logic.

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

INSERT INTO beats (beat_url, beat_title, published_at, date_range_raw, scraped_at) VALUES
    ('https://police.byu.edu/beat/a', 'Police Beat - 06/16/2026', '2026-06-16', '06/16/2026', now()),
    ('https://police.byu.edu/beat/b', 'Police Beat - 06/17/2026', '2026-06-17', '06/17/2026', now()),
    ('https://police.byu.edu/beat/c', 'Police Beat - 06/22/2026', '2026-06-22', '06/22/2026', now())
ON CONFLICT (beat_url) DO NOTHING;

INSERT INTO incidents (
    raw_text_hash, beat_url, incident_type, incident_text,
    location_zone, location_confidence, location_source,
    is_multi_date_beat, earliest_date, latest_date
) VALUES
    ('hash_a', 'https://police.byu.edu/beat/a', 'Fire Alarm', 'Alarm at the HBLL.',
     'ACADEMIC_CORE', 'HIGH', 'landmark', false, '2026-06-16', '2026-06-16'),
    ('hash_b', 'https://police.byu.edu/beat/b', 'Medical', 'Response at Heritage Halls.',
     'DORMS_HERITAGE', 'HIGH', 'landmark', false, '2026-06-17', '2026-06-17'),
    ('hash_c', 'https://police.byu.edu/beat/c', 'Traffic Accident', 'Accident with no stated location.',
     'UNKNOWN', 'NONE', 'none', false, '2026-06-22', '2026-06-22'),
    ('hash_d', 'https://police.byu.edu/beat/c', 'Theft', 'Bike taken near the stadium.',
     'STADIUM_AREA', 'HIGH', 'landmark', false, '2026-06-22', '2026-06-22')
ON CONFLICT (raw_text_hash) DO NOTHING;

INSERT INTO incident_dates (raw_text_hash, incident_date) VALUES
    ('hash_a', '2026-06-16'),
    ('hash_b', '2026-06-17'),
    ('hash_c', '2026-06-22'),
    ('hash_d', '2026-06-22')
ON CONFLICT DO NOTHING;
