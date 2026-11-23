-- Intermediate: one row per person, with the facts the checks keep asking for:
-- their level, whether they are employed on the as-of date, and when they last
-- moved or were rehired.

with employees as (

    select * from {{ ref('stg_employees') }}

),

periods as (

    select * from {{ ref('int_employment_periods') }}

),

events as (

    select * from {{ ref('stg_hr_events') }}

),

-- Employed on the as-of date: a period has started and hasn't ended before it.
employed_now as (

    select distinct employee_hash
    from periods
    where start_date <= date('{{ var("as_of_date") }}')
      and (last_day is null or last_day >= date('{{ var("as_of_date") }}'))

),

latest_events as (

    select
        employee_hash,
        max(case when event_type = 'mover'  then event_date end) as last_move_date,
        max(case when event_type = 'rehire' then event_date end) as rehire_date
    from events
    group by employee_hash

)

select
    employees.employee_hash,
    employees.department,
    employees.job_title,

    -- "Level" in the rule book, matched case-insensitively.
    case
        when starts_with(lower(employees.job_title), 'head of')
          or starts_with(lower(employees.job_title), 'acting head of') then 'head'
        when starts_with(lower(employees.job_title), 'deputy head')
          or lower(employees.job_title) = 'team lead'                  then 'lead'
        else 'staff'
    end                                         as level,

    employees.employment_type,                  -- as first hired; see periods for a rehire's type
    employees.hire_date,
    employees.termination_date,                 -- the roster's leaving date, kept after a rehire
    employed_now.employee_hash is not null      as is_employed,
    latest_events.last_move_date,
    latest_events.rehire_date

from employees
left join employed_now
    on employees.employee_hash = employed_now.employee_hash
left join latest_events
    on employees.employee_hash = latest_events.employee_hash
