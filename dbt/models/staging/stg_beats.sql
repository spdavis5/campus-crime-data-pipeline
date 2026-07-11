-- One row per police-beat page.
select
    beat_url,
    nullif(trim(beat_title), '')    as beat_title,
    nullif(trim(published_at), '')  as published_at,
    date_range_raw,
    scraped_at
from {{ source('raw', 'beats') }}
