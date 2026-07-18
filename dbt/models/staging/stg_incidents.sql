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
    -- Best single-date estimate for a beat. Normally the earliest candidate day.
    -- But a police beat covers only a day or two, so a date span wider than a
    -- month means the source title has a typo'd year (real cases seen:
    -- "06/21/2025 - 06/22/2005" and "10/07/20203 to 10/09/2023"). In that case the
    -- earlier date is the corrupt one, so we fall back to the most recent date.
    case
        when earliest_date is not null and latest_date is not null
             and (latest_date - earliest_date) > 31
        then latest_date
        else earliest_date
    end                                    as occurred_date
from {{ source('raw', 'incidents') }}
