-- Check 4: dormant privileged account. One row per account.
-- Rule: inventory/check_rules.md, section 4.
--
-- In scope: accounts active on the as-of date that hold at least one open
-- privileged grant, and were created at least 30 days before the as-of date.
-- Dormant: no login in the 30 days ending on the as-of date (1 to 30 September).
-- An account with no login in the whole 90-day history is labelled as such,
-- with no last-login date, because the data can't say how long it has been.
-- Not testable on this data: failed logins and locked accounts.

with privileged_roles as (

    -- The open privileged roles on each account, as readable text.
    select
        account_id,
        string_agg(role, ', ' order by role) as privileged_roles
    from {{ ref('int_grants') }}
    where is_open
      and is_privileged
    group by account_id

),

in_scope as (

    select
        accounts.*,
        privileged_roles.privileged_roles

    from {{ ref('int_accounts') }} as accounts
    join privileged_roles                   -- inner join: only accounts with open privileged access
        on privileged_roles.account_id = accounts.account_id

    where accounts.status = 'active'
      and date_diff(date('{{ var("as_of_date") }}'), accounts.created_date, day) >= 30

)

select
    account_id,
    employee_hash,
    system,
    privileged_roles,
    created_date,
    last_login_date,                         -- empty: no login in the 90-day history
    date_diff(date('{{ var("as_of_date") }}'), last_login_date, day) as days_since_last_login,

    case
        when last_login_date is null then 'No login in available history (90+ days)'
        else 'No login in the last 30 days'
    end as dormancy

from in_scope
-- No login from 1 September (the as-of date minus 29 days) up to the as-of date.
where last_login_date is null
   or last_login_date < date_sub(date('{{ var("as_of_date") }}'), interval 29 day)
