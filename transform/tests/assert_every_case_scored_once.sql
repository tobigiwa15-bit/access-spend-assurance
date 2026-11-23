-- Custom test: every answer-key case appears exactly once in the scored results.
-- Returns cases that are missing or appear more than once; zero rows means pass.
-- Like reconciling a control total: 151 cases in, 151 cases scored.

with scored as (

    select case_id, count(*) as times_scored
    from {{ ref('score_case_results') }}
    where case_id is not null
    group by case_id

)

select
    answer_key.case_id,
    coalesce(scored.times_scored, 0) as times_scored

from {{ ref('score_answer_key') }} as answer_key
left join scored
    on scored.case_id = answer_key.case_id
where coalesce(scored.times_scored, 0) != 1
