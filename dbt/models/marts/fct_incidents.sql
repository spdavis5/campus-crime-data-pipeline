-- Incident fact. Grain: one row per incident. Foreign keys point at dim_date
-- (occurred_date), dim_location (location_zone), and dim_incident_type
-- (incident_type). incident_count is the additive measure; incident_text is kept
-- as a degenerate attribute so the dashboard can show narratives without a join.
select
    i.incident_id,
    i.occurred_date,
    i.location_zone,
    i.incident_type,
    i.beat_url,
    i.location_source,
    i.location_confidence,
    i.incident_text,
    1 as incident_count
from {{ ref('stg_incidents') }} i
