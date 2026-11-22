-- Staging: the HR roster, with proper types and personal data protected.
--
-- Protected:
--   employee_id, manager_id  -> keyed hashes (hash_pii)
--   bank_account_number      -> masked for display, plus a keyed hash for matching
-- Dropped, because no check and no agent tool needs them (data minimisation):
--   full_name, email
--
-- Everything downstream reads this model, never the raw table.

with source as (

    select * from {{ source('raw', 'employees') }}

)

select
    {{ hash_pii('employee_id') }}             as employee_hash,
    {{ hash_pii('manager_id') }}              as manager_hash,
    department,
    job_title,
    employment_type,
    cast(hire_date as date)                   as hire_date,
    cast(termination_date as date)            as termination_date,
    {{ mask_account('bank_account_number') }} as bank_account_masked,
    {{ hash_pii('bank_account_number') }}     as bank_account_hash

from source
