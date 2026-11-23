-- Intermediate: every grant ever made, with whose it is, which system it is in,
-- and what the role allows. One row per grant.
--
-- Checks 1 to 5 all need this same join, so it is written once here instead of
-- five times inside the checks.

with grants as (

    select * from {{ ref('stg_access_grants') }}

),

accounts as (

    select * from {{ ref('stg_accounts') }}

),

roles as (

    select * from {{ ref('stg_roles') }}

)

select
    grants.grant_id,
    grants.account_id,
    accounts.employee_hash,
    accounts.system,
    accounts.status        as account_status,
    grants.role,
    roles.is_privileged,
    roles.sod_function,                          -- empty if the role has no SoD relevance
    grants.grant_type,
    grants.approver_hash,
    grants.approval_date,
    grants.granted_date,
    grants.revoked_date,

    -- "Held" in the rule book: from granted_date up to, but not including,
    -- held_until. An open grant is held up to and including the as-of date,
    -- so its held_until is the day after.
    coalesce(
        grants.revoked_date,
        date_add(date('{{ var("as_of_date") }}'), interval 1 day)
    )                      as held_until,

    grants.revoked_date is null as is_open

from grants
-- Inner joins are safe here: the staging relationships tests already prove
-- every grant has an account and a known role, so no grant is dropped.
join accounts
    on grants.account_id = accounts.account_id
join roles
    on grants.role = roles.role
