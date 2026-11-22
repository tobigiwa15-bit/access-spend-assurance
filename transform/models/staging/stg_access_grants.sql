-- Staging: every role ever granted, with its approval and removal.
--
-- Protected:
--   approver_id -> keyed hash (same macro, so it matches employee_hash elsewhere)

with source as (

    select * from {{ source('raw', 'access_grants') }}

)

select
    grant_id,
    account_id,
    role,
    grant_type,
    {{ hash_pii('approver_id') }} as approver_hash,
    cast(approval_date as date)   as approval_date,
    cast(granted_date as date)    as granted_date,
    cast(revoked_date as date)    as revoked_date   -- empty while the access is still open

from source
