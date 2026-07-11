-- One row per incident: light cleanup over the raw incidents table. The scrape
-- hash becomes the stable incident_id used as the fact grain downstream.
select
    raw_text_hash                          as incident_id,
    beat_url,
    nullif(trim(incident_type), '')        as incident_type,
    incident_text,
    location_zone,
    location_confidence,
    location_source,
    is_multi_date_beat,
    earliest_date,
    latest_date,
    -- Best single-date estimate for a multi-day beat: the earliest candidate day.
    earliest_date                          as occurred_date
from {{ source('raw', 'incidents') }}
