-- Intermediate: every account with its login activity. One row per account.
--
-- Used by check 1 (was a leaver's account used?) and check 4 (is a privileged
-- account dormant?). Login data covers only the 90 days to the as-of date, so an
-- empty last_login_date means "no login in that window", not "never used".

with accounts as (

    select * from {{ ref('stg_accounts') }}

),

logins as (

    select
        account_id,
        max(login_date) as last_login_date,
        count(*)        as login_days         -- one login row per account per day
    from {{ ref('stg_logins') }}
    group by account_id

)

select
    accounts.account_id,
    accounts.employee_hash,
    accounts.system,
    accounts.status,
    accounts.created_date,
    accounts.disabled_date,
    logins.last_login_date,
    coalesce(logins.login_days, 0) as login_days

from accounts
-- Left join: accounts with no logins must stay in, because they are exactly
-- what the dormancy check looks for.
left join logins
    on accounts.account_id = logins.account_id
