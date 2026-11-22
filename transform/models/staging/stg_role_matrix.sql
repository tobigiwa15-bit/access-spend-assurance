-- Staging: the roles each department should have, by level (staff, lead, head, admin).

with source as (

    select * from {{ source('raw', 'role_matrix') }}

)

select
    department,
    level,
    role

from source
