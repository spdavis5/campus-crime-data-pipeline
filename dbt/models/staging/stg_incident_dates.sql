-- Bridge: one row per (incident, candidate date). Preserves the full date
-- expansion for multi-day beats even though the fact uses a single occurred_date.
select
    raw_text_hash   as incident_id,
    incident_date
from {{ source('raw', 'incident_dates') }}
