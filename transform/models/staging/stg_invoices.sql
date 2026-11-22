-- Staging: supplier invoices in the audit period.
--
-- Protected:
--   entered_by -> keyed hash

with source as (

    select * from {{ source('raw', 'invoices') }}

)

select
    invoice_id,
    vendor_id,
    po_id,
    vendor_invoice_number,
    cast(invoice_date as date)   as invoice_date,
    cast(amount as numeric)      as amount,
    {{ hash_pii('entered_by') }} as entered_by_hash

from source
