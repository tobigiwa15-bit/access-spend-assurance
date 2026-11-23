-- Scoring: the outcome for every item a check examined, plus any answer-key
-- case outside that population. One row per check per entity.
--
-- Outcome (inventory/scoring_method.md):
--   TP               flagged, and a seeded issue
--   FN               a seeded issue, not flagged
--   FP (look-alike)  flagged, but a look-alike
--   FP (other)       flagged, and neither seeded nor a look-alike
--   TN (look-alike)  a look-alike, correctly not flagged
--   TN               everything else in the population
-- This row-level table is what the false positives and misses are reviewed from.

with population as (

    select check_name, entity_key, true as in_population
    from {{ ref('score_population') }}

),

answer_key as (

    select * from {{ ref('score_answer_key') }}

),

flags as (

    select distinct check_name, entity_key, true as is_flagged
    from {{ ref('score_flags') }}

),

-- Every item to score: the population, plus any answer-key case outside it
-- (a planted issue outside a check's scope still counts as missed).
items as (

    select check_name, entity_key from population
    union distinct
    select check_name, entity_key from answer_key

)

select
    items.check_name,
    items.entity_key,
    coalesce(population.in_population, false) as in_population,
    coalesce(flags.is_flagged, false)         as is_flagged,
    answer_key.case_id,
    answer_key.case_type,
    answer_key.description,

    case
        when flags.is_flagged and answer_key.case_type = 'seeded_issue' then 'TP'
        when answer_key.case_type = 'seeded_issue'                      then 'FN'
        when flags.is_flagged and answer_key.case_type = 'look_alike'   then 'FP (look-alike)'
        when flags.is_flagged                                           then 'FP (other)'
        when answer_key.case_type = 'look_alike'                        then 'TN (look-alike)'
        else 'TN'
    end as outcome

from items
left join population
    on  population.check_name = items.check_name
    and population.entity_key = items.entity_key
left join flags
    on  flags.check_name = items.check_name
    and flags.entity_key = items.entity_key
left join answer_key
    on  answer_key.check_name = items.check_name
    and answer_key.entity_key = items.entity_key
