-- Staging: purchase orders in the audit period.
--
-- Protected:
--   requested_by, approved_by -> keyed hashes
-- Amounts become NUMERIC (exact decimals), not FLOAT, as money should be.

with source as (

    select * from {{ source('raw', 'purchase_orders') }}

)

select
    po_id,
    vendor_id,
    cast(po_date as date)          as po_date,
    cast(amount as numeric)        as amount,
    {{ hash_pii('requested_by') }} as requested_by_hash,
    {{ hash_pii('approved_by') }}  as approved_by_hash

from source
