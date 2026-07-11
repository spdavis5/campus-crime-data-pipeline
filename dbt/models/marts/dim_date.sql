-- Date dimension spanning the incident data, enriched with BYU academic-calendar
-- context. The spine is generated from the observed incident date range; each day
-- is tagged with the semester it falls in and boolean flags for finals, breaks,
-- and home game days by joining the academic_calendar period ranges.
with bounds as (
    select
        min(occurred_date) as min_date,
        max(occurred_date) as max_date
    from {{ ref('stg_incidents') }}
    where occurred_date is not null
),

spine as (
    select generate_series(min_date, max_date, interval '1 day')::date as date_day
    from bounds
),

calendar as (
    select * from {{ ref('academic_calendar') }}
)

select
    d.date_day,
    extract(isodow from d.date_day)::int              as day_of_week,
    trim(to_char(d.date_day, 'Day'))                  as day_name,
    extract(isodow from d.date_day) in (6, 7)         as is_weekend,
    (
        select c.label from calendar c
        where c.period_type = 'SEMESTER'
          and d.date_day between c.start_date and c.end_date
        limit 1
    )                                                 as semester,
    exists (
        select 1 from calendar c
        where c.period_type = 'FINALS'
          and d.date_day between c.start_date and c.end_date
    )                                                 as is_finals,
    exists (
        select 1 from calendar c
        where c.period_type = 'BREAK'
          and d.date_day between c.start_date and c.end_date
    )                                                 as is_break,
    exists (
        select 1 from calendar c
        where c.period_type = 'GAME_DAY'
          and d.date_day between c.start_date and c.end_date
    )                                                 as is_game_day
from spine d
