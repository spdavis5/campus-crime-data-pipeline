-- Incident-type dimension. One row per distinct reported type, grouped into a
-- coarse category so the dashboard can roll up the long tail of specific types.
with types as (
    select distinct incident_type
    from {{ ref('stg_incidents') }}
    where incident_type is not null
)

select
    incident_type,
    case
        when incident_type ~* 'alarm'                                   then 'Alarm'
        when incident_type ~* 'medical|seizure|chest|unconscious|faint|injur|overdose' then 'Medical'
        when incident_type ~* 'traffic|accident|parking|vehicle|hit and run'  then 'Traffic'
        when incident_type ~* 'theft|burglar|robber|stolen|fraud|larceny|mischief' then 'Property'
        when incident_type ~* 'welfare|assist|informa|found|lost|lockout|escort' then 'Service'
        when incident_type ~* 'trespass|suspicious|disorder|drug|alcohol|assault|harass|disturbance' then 'Conduct/Crime'
        else 'Other'
    end as incident_category
from types
