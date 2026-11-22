-- Staging: the vendor master file.
--
-- Protected:
--   bank_account_number      -> masked for display, plus a keyed hash for matching
--                               (same macros as stg_employees, so the bank-match
--                               check can join on bank_account_hash)
--   created_by, approved_by  -> keyed hashes
-- Kept: vendor_name. These are company names, not personal data.

with source as (

    select * from {{ source('raw', 'vendors') }}

)

select
    vendor_id,
    vendor_name,
    category,
    billing,
    bank_name,
    {{ mask_account('bank_account_number') }} as bank_account_masked,
    {{ hash_pii('bank_account_number') }}     as bank_account_hash,
    cast(created_date as date)                as created_date,
    {{ hash_pii('created_by') }}              as created_by_hash,
    cast(approved_date as date)               as approved_date,
    {{ hash_pii('approved_by') }}             as approved_by_hash

from source
