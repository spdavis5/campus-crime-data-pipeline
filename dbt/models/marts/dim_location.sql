-- Location (campus zone) dimension. One row per zone that appears in the data,
-- with a friendly label and a few groupings useful for the dashboard.
with zones as (
    select distinct location_zone as zone
    from {{ ref('stg_incidents') }}
)

select
    zone as location_zone,
    case zone
        when 'ACADEMIC_CORE'     then 'Academic Core'
        when 'ENGINEERING_NORTH' then 'Engineering (North)'
        when 'BUSINESS_SOUTH'    then 'Business (South)'
        when 'STUDENT_SERVICES'  then 'Student Services'
        when 'STADIUM_AREA'      then 'Stadium / Athletics'
        when 'DORMS_HELAMAN'     then 'Helaman Halls'
        when 'DORMS_HERITAGE'    then 'Heritage Halls'
        when 'WYVIEW_WYMOUNT'    then 'Wyview / Wymount'
        when 'MTC'               then 'Missionary Training Center'
        when 'SERVICE_SUPPORT'   then 'Service / Support'
        when 'OFF_CAMPUS'        then 'Off Campus'
        else 'Unknown'
    end                                                          as zone_label,
    zone in ('DORMS_HELAMAN', 'DORMS_HERITAGE', 'WYVIEW_WYMOUNT') as is_residential,
    zone in ('ACADEMIC_CORE', 'ENGINEERING_NORTH', 'BUSINESS_SOUTH') as is_academic,
    zone not in ('OFF_CAMPUS', 'MTC', 'UNKNOWN')                 as is_on_campus,
    zone = 'UNKNOWN'                                             as is_unknown
from zones
