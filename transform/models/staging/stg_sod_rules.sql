-- Staging: the SoD matrix. Each row is a pair of functions one person must not hold together.

with source as (

    select * from {{ source('raw', 'sod_rules') }}

)

select
    function_a,
    function_b,
    risk

from source
