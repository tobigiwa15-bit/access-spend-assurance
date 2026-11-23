-- Custom test: every flagged entity must be in its check's population.
-- Returns the flags that fall outside; zero rows means pass.
--
-- Why: the population repeats each check's scope in a second place. If the two
-- ever disagreed, a check could flag something "outside" what it examines, and
-- the false-positive rate would be divided by the wrong number. This catches it.

select
    flags.check_name,
    flags.entity_key

from {{ ref('score_flags') }} as flags
left join {{ ref('score_population') }} as population
    on  population.check_name = flags.check_name
    and population.entity_key = flags.entity_key
where population.entity_key is null
