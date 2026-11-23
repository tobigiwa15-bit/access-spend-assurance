-- Scoring: the answer key, ready to match against the checks. One row per case.
--
-- Protected:
--   entity_id for people (check 3)         -> keyed hash, so it matches employee_hash
--   employee IDs inside the descriptions  -> replaced with "[employee]"; the hash is
--                                             kept in related_employee_hash
-- Every other entity (accounts, grants, invoices, POs, payments, vendors) is a
-- system ID, not personal data, so it is used as it is.

with source as (

    select * from {{ source('answer_key', 'answer_key') }}

)

select
    case_id,
    check_name,
    case_type,                                     -- seeded_issue or look_alike
    entity_type,

    case
        when entity_type = 'employee' then {{ hash_pii('entity_id') }}
        else entity_id
    end                                            as entity_key,

    -- Raw employee IDs look like E12345. The description keeps its meaning
    -- without them, and the person can still be followed by hash.
    regexp_replace(description, r'E\d{5}', '[employee]')            as description,
    {{ hash_pii("regexp_extract(description, r'E\\d{5}')") }}        as related_employee_hash

from source
