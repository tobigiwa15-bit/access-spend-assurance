-- Staging: one account per person per system.
--
-- Protected:
--   employee_id -> keyed hash
-- Dropped (data minimisation):
--   username, which is built from the person's name (e.g. daniel.okonkwo)

with source as (

    select * from {{ source('raw', 'accounts') }}

)

select
    account_id,
    {{ hash_pii('employee_id') }} as employee_hash,
    system,
    status,
    cast(created_date as date)    as created_date,
    cast(disabled_date as date)   as disabled_date

from source
