-- Custom test: every entity in the answer key must exist in the staging data.
-- Returns the cases whose entity can't be found; zero rows means pass.
--
-- Why: scoring matches check rows to the key by these IDs. If a key couldn't
-- be found (say the hash for people came out differently), every case would
-- silently score as "missed", and the check would look bad for the wrong reason.

with key as (

    select * from {{ ref('score_answer_key') }}

),

known_entities as (

    select 'account'        as entity_type, account_id    as entity_key from {{ ref('stg_accounts') }}         union all
    select 'grant',                         grant_id                    from {{ ref('stg_access_grants') }}    union all
    select 'employee',                      employee_hash               from {{ ref('stg_employees') }}        union all
    select 'invoice',                       invoice_id                  from {{ ref('stg_invoices') }}         union all
    select 'purchase_order',                po_id                       from {{ ref('stg_purchase_orders') }}  union all
    select 'vendor',                        vendor_id                   from {{ ref('stg_vendors') }}          union all
    select 'payment',                       payment_id                  from {{ ref('stg_payments') }}

)

select
    key.case_id,
    key.check_name,
    key.entity_type,
    key.entity_key

from key
left join known_entities
    on  known_entities.entity_type = key.entity_type
    and known_entities.entity_key  = key.entity_key
where known_entities.entity_key is null
