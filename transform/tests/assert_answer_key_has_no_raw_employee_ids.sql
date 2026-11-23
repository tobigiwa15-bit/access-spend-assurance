-- Custom test: no raw employee ID (like E12345) survives in the scored answer
-- key. Returns any case that still has one; zero rows means pass.
-- This proves the masking in score_answer_key worked, instead of assuming it.

select
    case_id,
    entity_key,
    description

from {{ ref('score_answer_key') }}
where regexp_contains(entity_key, r'^E\d{5}$')
   or regexp_contains(description, r'E\d{5}')
