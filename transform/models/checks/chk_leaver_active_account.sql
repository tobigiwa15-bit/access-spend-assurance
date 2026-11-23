-- Check 1: leaver with active account. One row per account.
-- Rule: inventory/check_rules.md, section 1.
--
-- An account is an exception if it worked past the end of the grace period
-- after its owner's termination date:
--   Open           still active on the as-of date
--   Disabled late  disabled, but only after the grace period ended
-- Grace period: 1 business day, or none for an account that held privileged
-- access after the termination date.
-- Excluded: a rehired person in an ongoing engagement whose open access all
-- matches their entitled roles.

with leavers as (

    select * from {{ ref('int_employees') }}
    where termination_date is not null

),

leaver_accounts as (

    select
        accounts.account_id,
        accounts.employee_hash,
        accounts.system,
        accounts.status,
        accounts.disabled_date,
        leavers.termination_date,
        leavers.is_employed,
        leavers.rehire_date,

        -- "Account active": the disabled date is the first day gone, so a
        -- disabled account last worked the day before it.
        case
            when accounts.status = 'active' then date('{{ var("as_of_date") }}')
            else date_sub(accounts.disabled_date, interval 1 day)
        end as last_active_date

    from {{ ref('int_accounts') }} as accounts
    join leavers
        on accounts.employee_hash = leavers.employee_hash

),

-- Accounts that held an open privileged grant at any point from the
-- termination date to the last day the account worked.
privileged_after_termination as (

    select distinct leaver_accounts.account_id
    from leaver_accounts
    join {{ ref('int_grants') }} as grants
        on grants.account_id = leaver_accounts.account_id
    where grants.is_privileged
      and grants.granted_date <= leaver_accounts.last_active_date   -- started before the account stopped
      and grants.held_until    > leaver_accounts.termination_date   -- still held on or after the termination date

),

logins_after_termination as (

    select
        leaver_accounts.account_id,
        count(*)              as login_days,
        max(logins.login_date) as last_login_date
    from leaver_accounts
    join {{ ref('stg_logins') }} as logins
        on logins.account_id = leaver_accounts.account_id
    where logins.login_date > leaver_accounts.termination_date
    group by leaver_accounts.account_id

),

-- Accounts with at least one open grant the owner is not entitled to.
-- A rehire with any such grant loses the exclusion.
accounts_with_unentitled_access as (

    select distinct grants.account_id
    from {{ ref('int_grants') }} as grants
    left join {{ ref('int_entitlements') }} as entitlements
        on  entitlements.employee_hash = grants.employee_hash
        and entitlements.role          = grants.role
    where grants.is_open
      and entitlements.role is null

),

assessed as (

    select
        leaver_accounts.*,
        privileged.account_id is not null as is_privileged,

        -- End of the grace period. Privileged: none, so it ends on the
        -- termination date. Otherwise 1 business day later: Friday -> Monday,
        -- Saturday -> Monday, any other day -> the next day.
        -- (BigQuery dayofweek: 1 = Sunday ... 6 = Friday, 7 = Saturday.)
        case
            when privileged.account_id is not null then leaver_accounts.termination_date
            else date_add(
                leaver_accounts.termination_date,
                interval case extract(dayofweek from leaver_accounts.termination_date)
                             when 6 then 3
                             when 7 then 2
                             else 1
                         end day
            )
        end as grace_end_date,

        coalesce(logins.login_days, 0) as login_days_after_termination,
        logins.last_login_date         as last_login_after_termination,

        -- Rehire exclusion: back in an ongoing engagement after leaving, the
        -- account is still in use, and every open grant on it is entitled.
        -- coalesce: for someone never rehired, rehire_date is empty, so the
        -- comparison gives NULL rather than false. Without it, "not NULL" in
        -- the final filter is also NULL, and every non-rehire would vanish.
        coalesce(
            leaver_accounts.rehire_date > leaver_accounts.termination_date
            and leaver_accounts.is_employed
            and leaver_accounts.status = 'active'
            and unentitled.account_id is null,
            false
        ) as is_excluded_rehire

    from leaver_accounts
    left join privileged_after_termination as privileged
        on privileged.account_id = leaver_accounts.account_id
    left join logins_after_termination as logins
        on logins.account_id = leaver_accounts.account_id
    left join accounts_with_unentitled_access as unentitled
        on unentitled.account_id = leaver_accounts.account_id

)

select
    account_id,
    employee_hash,
    system,
    case when status = 'active' then 'Open' else 'Disabled late' end as exception_type,
    termination_date,
    grace_end_date,
    last_active_date,
    date_diff(last_active_date, grace_end_date, day)                 as days_late,
    is_privileged,
    login_days_after_termination,
    last_login_after_termination,

    case
        when login_days_after_termination > 0                         then 'Critical'
        when is_privileged
          or system in ('core_banking', 'payments_console')           then 'High'
        else 'Medium'
    end as severity

from assessed
where last_active_date > grace_end_date      -- worked past the grace period
  and not is_excluded_rehire
