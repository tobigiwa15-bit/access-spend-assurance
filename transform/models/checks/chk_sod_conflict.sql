-- Check 3: segregation-of-duties conflict. One row per person.
-- Rule: inventory/check_rules.md, section 3.
--
-- A person is flagged if they held both functions of any pair in stg_sod_rules
-- at the same time, for at least one day in the review period, across any
-- systems. A grant is held from granted_date up to, but not including,
-- held_until (int_grants).
--   Current     both functions held on the as-of date
--   Historical  held together in the review period, but not on the as-of date
--   Both        the person has at least one of each
-- Current conflicts rank above historical ones (severity High vs Medium).

with grants as (

    select * from {{ ref('int_grants') }}
    where sod_function is not null

),

rules as (

    select * from {{ ref('stg_sod_rules') }}

),

-- Every pair of grants, held by the same person, that gives them both functions
-- of a rule. The overlap is clipped to the review period. Like the grants, its
-- end is exclusive: the first day they no longer hold both.
grant_pairs as (

    select
        grant_a.employee_hash,
        rules.function_a,
        rules.function_b,
        grant_a.system as system_a,
        grant_b.system as system_b,
        greatest(grant_a.granted_date, grant_b.granted_date,
                 date('{{ var("review_start") }}'))                          as overlap_start,
        least(grant_a.held_until, grant_b.held_until,
              date_add(date('{{ var("as_of_date") }}'), interval 1 day))      as overlap_end

    from rules
    join grants as grant_a
        on grant_a.sod_function = rules.function_a
    join grants as grant_b
        on  grant_b.sod_function  = rules.function_b
        and grant_b.employee_hash = grant_a.employee_hash

),

conflicts as (

    select
        *,
        -- The overlap runs through the as-of date, so both are held today.
        overlap_end > date('{{ var("as_of_date") }}') as is_current

    from grant_pairs
    where overlap_start < overlap_end      -- at least one day held together

),

by_person as (

    select
        employee_hash,
        logical_or(is_current)                  as has_current,
        logical_or(not is_current)              as has_historical,
        logical_or(system_a != system_b)        as is_cross_system,
        count(*)                                as conflicting_grant_pairs,
        string_agg(
            distinct concat(function_a, ' (', system_a, ') + ', function_b, ' (', system_b, ')'),
            '; '
            order by concat(function_a, ' (', system_a, ') + ', function_b, ' (', system_b, ')')
        )                                       as conflicting_functions

    from conflicts
    group by employee_hash

)

select
    employee_hash,
    case
        when has_current and has_historical then 'Both'
        when has_current                    then 'Current'
        else 'Historical'
    end                                     as conflict_status,
    conflicting_functions,
    conflicting_grant_pairs,
    is_cross_system,
    case when has_current then 'High' else 'Medium' end as severity

from by_person
