-- Staging: joiner, mover, leaver and rehire events, with the employee pseudonymised.

with source as (

    select * from {{ source('raw', 'hr_events') }}

)

select
    event_id,
    {{ hash_pii('employee_id') }} as employee_hash,
    event_type,
    cast(event_date as date)      as event_date,
    from_department,
    to_department,
    employment_type

from source
