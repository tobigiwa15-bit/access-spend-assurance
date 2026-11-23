-- Check 2: privileged access without approval. One row per grant.
-- Rule: inventory/check_rules.md, section 2.
--
-- In scope: privileged grants that are open on the as-of date (whenever made),
-- or were made during the review period (even if since removed).
--
-- Standard grant fails if:   no approval on record, self-approved (both High),
--                            or approved after the grant date (Medium).
-- Emergency grant fails if:  no approval, self-approved, approved later than the
--                            next business day, or not removed within 3 calendar
--                            days. Any failure is High.
-- Not testable on this data: the approver's authority, and who set up the access.

with grants as (

    select * from {{ ref('int_grants') }}
    where is_privileged
      and (
          is_open
          or granted_date between date('{{ var("review_start") }}') and date('{{ var("as_of_date") }}')
      )

),

tested as (

    select
        grants.*,

        -- An approval needs both an approver and a date. Without a date there is
        -- no way to show it came before (or soon enough after) the grant.
        (approver_hash is not null and approval_date is not null) as has_approval,
        coalesce(approver_hash = employee_hash, false)             as is_self_approved,

        -- Standard: the approval must be dated on or before the grant.
        approval_date > granted_date                               as approved_after_grant,

        -- Emergency: approval due by the end of the next business day (T+1).
        -- The macro returns 0 when the approval is on or before the grant date.
        {{ business_days_between('granted_date', 'approval_date') }} > 1 as approved_late,

        -- Emergency: removed within 3 calendar days. A grant still open is only
        -- a failure once its 3 days have passed by the as-of date.
        date_diff(
            coalesce(revoked_date, date('{{ var("as_of_date") }}')),
            granted_date,
            day
        ) > 3                                                       as not_removed_in_time

    from grants

),

reasons as (

    select
        tested.*,

        -- Every reason the grant fails, joined into one readable string.
        -- array_to_string skips the NULLs left by conditions that didn't apply.
        array_to_string([
            if(not has_approval,                                         'no approval on record',  null),
            if(has_approval and is_self_approved,                        'approved by the grantee', null),
            if(grant_type = 'standard'  and has_approval and approved_after_grant, 'approved after the grant', null),
            if(grant_type = 'emergency' and has_approval and approved_late,        'emergency approval later than the next business day', null),
            if(grant_type = 'emergency' and not_removed_in_time,         'emergency access not removed within 3 days', null)
        ], '; ') as failure_reasons

    from tested

)

select
    grant_id,
    account_id,
    employee_hash,
    system,
    role,
    grant_type,
    approver_hash,
    approval_date,
    granted_date,
    revoked_date,
    is_open,
    failure_reasons,

    case
        when grant_type = 'emergency'                 then 'High'
        when not has_approval or is_self_approved     then 'High'
        else 'Medium'                                 -- standard, approved after the grant
    end as severity

from reasons
where failure_reasons != ''          -- at least one reason applies
