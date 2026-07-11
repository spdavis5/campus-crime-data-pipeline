-- Daily rollup for the dashboard. Grain: one row per calendar day in range, with
-- incident counts and the academic-calendar context for that day. Built from
-- dim_date (left) so days with zero incidents still appear in trend lines.
select
    d.date_day,
    d.day_name,
    d.is_weekend,
    d.semester,
    d.is_finals,
    d.is_break,
    d.is_game_day,
    count(f.incident_id)                                            as total_incidents,
    count(f.incident_id) filter (where f.location_zone <> 'UNKNOWN') as located_incidents,
    count(distinct f.location_zone)
        filter (where f.location_zone <> 'UNKNOWN')                 as distinct_zones
from {{ ref('dim_date') }} d
left join {{ ref('fct_incidents') }} f
    on f.occurred_date = d.date_day
group by 1, 2, 3, 4, 5, 6, 7
order by d.date_day
