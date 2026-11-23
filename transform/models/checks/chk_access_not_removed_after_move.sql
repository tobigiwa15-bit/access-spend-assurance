-- Check 5: access not removed after a role change. One row per grant.
-- Rule: inventory/check_rules.md, section 5.
--
-- Old access: a grant made before the person's most recent move date, for a
-- role they are not entitled to now (int_entitlements). Only current employees.
-- Grace period: 3 calendar days after the move date. None for privileged old
-- access, or old access whose function conflicts (stg_sod_rules) with a function
-- of the person's new entitled roles.
-- An exception is old access held on any day after the grace period:
--   Open          still held on the as-of date
--   Removed late  removed, but only after the grace period ended
-- Not testable on this data: approved handover extensions.

with movers as (

    select * from {{ ref('int_employees') }}
    where is_employed
      and last_move_date is not null

),

-- Old access: granted before the latest move, and not an entitled role now.
old_grants as (

    select
        grants.*,
        movers.last_move_date as move_date

    from {{ ref('int_grants') }} as grants
    join movers
        on movers.employee_hash = grants.employee_hash
    left join {{ ref('int_entitlements') }} as entitlements
        on  entitlements.employee_hash = grants.employee_hash
        and entitlements.role          = grants.role

    where grants.granted_date < movers.last_move_date
      and entitlements.role is null             -- not entitled in the new role

),

-- The SoD functions of each person's new entitled roles.
new_functions as (

    select
        entitlements.employee_hash,
        roles.sod_function
    from {{ ref('int_entitlements') }} as entitlements
    join {{ ref('stg_roles') }} as roles
        on roles.role = entitlements.role
    where roles.sod_function is not null

),

-- Old grants whose function makes an SoD pair with a new function, in either
-- order of the rule.
sod_conflicting_grants as (

    select distinct old_grants.grant_id
    from old_grants
    join {{ ref('stg_sod_rules') }} as rules
        on old_grants.sod_function in (rules.function_a, rules.function_b)
    join new_functions
        on  new_functions.employee_hash = old_grants.employee_hash
        and new_functions.sod_function  = case
                                              when old_grants.sod_function = rules.function_a then rules.function_b
                                              else rules.function_a
                                          end

),

assessed as (

    select
        old_grants.*,
        sod.grant_id is not null as conflicts_with_new_role,

        -- The last day the old access was held (held_until is the first day gone).
        date_sub(old_grants.held_until, interval 1 day) as last_held_date,

        -- End of the grace period: the move date itself if there is no grace,
        -- otherwise 3 calendar days later.
        case
            when old_grants.is_privileged or sod.grant_id is not null then old_grants.move_date
            else date_add(old_grants.move_date, interval 3 day)
        end as grace_end_date

    from old_grants
    left join sod_conflicting_grants as sod
        on sod.grant_id = old_grants.grant_id

)

select
    grant_id,
    employee_hash,
    account_id,
    system,
    role,
    granted_date,
    revoked_date,
    move_date,
    grace_end_date,
    case when is_open then 'Open' else 'Removed late' end as exception_type,
    date_diff(last_held_date, grace_end_date, day)      as days_late,
    is_privileged,
    conflicts_with_new_role

from assessed
where last_held_date > grace_end_date       -- held on a day after the grace period
