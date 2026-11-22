-- Staging: supplier payments in the audit period.
--
-- Protected:
--   approved_by -> keyed hash

with source as (

    select * from {{ source('raw', 'payments') }}

)

select
    payment_id,
    vendor_id,
    invoice_id,                                     -- empty if there is no invoice
    cast(payment_date as date)    as payment_date,
    cast(amount as numeric)       as amount,
    {{ hash_pii('approved_by') }} as approved_by_hash

from source
