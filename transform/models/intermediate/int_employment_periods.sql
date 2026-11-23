-- Intermediate: each stretch of time a person worked here. One row per period.
--
-- Why this exists: the roster keeps one row per person, so a leaver who was
-- rehired still shows their old termination date. Only the HR events show they
-- came back. A period starts with a joiner or rehire event, and ends with the
-- first leaver event on or after that start. No leaver event means it is ongoing.
--
-- Used by check 1 (is a leaver back under a new engagement?) and check 8 (was
-- the person employed on the day a vendor was paid?).

with events as (

    select * from {{ ref('stg_hr_events') }}

),

starts as (

    select
        employee_hash,
        event_type        as started_by,      -- joiner or rehire
        event_date        as start_date,
        employment_type
    from events
    where event_type in ('joiner', 'rehire')

),

leaves as (

    select
        employee_hash,
        event_date        as leave_date       -- the last working day
    from events
    where event_type = 'leaver'

)

select
    starts.employee_hash,
    starts.started_by,
    starts.employment_type,
    starts.start_date,
    -- The last working day, which still counts as employed. Empty if ongoing.
    -- Note: this end is inclusive, unlike held_until in int_grants, because
    -- HR records the last day worked, not the first day gone.
    min(leaves.leave_date) as last_day

from starts
left join leaves
    on  leaves.employee_hash = starts.employee_hash
    and leaves.leave_date   >= starts.start_date

group by
    starts.employee_hash,
    starts.started_by,
    starts.employment_type,
    starts.start_date
