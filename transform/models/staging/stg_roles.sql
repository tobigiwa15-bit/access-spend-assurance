-- Staging: the role catalogue. No personal data; only types change.

with source as (

    select * from {{ source('raw', 'roles') }}

)

select
    system,
    role,
    lower(is_privileged) = 'true' as is_privileged,   -- text 'True'/'False' to a real true/false
    sod_function,
    description

from source
