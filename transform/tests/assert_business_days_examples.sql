-- Custom test for the business_days_between macro: worked examples with known
-- answers, like testing a formula on a few hand-checked rows before trusting it.
-- Returns the examples where the macro gives the wrong answer; zero rows means pass.

with examples as (

    select date '2026-09-25' as start_date, date '2026-09-28' as end_date, 1 as expected, 'Fri to Mon'         as label union all
    select date '2026-09-25',               date '2026-09-27',             0,             'Fri to Sun'                  union all
    select date '2026-09-28',               date '2026-09-28',             0,             'same day'                    union all
    select date '2026-09-28',               date '2026-10-02',             4,             'Mon to Fri'                  union all
    select date '2026-09-25',               date '2026-10-02',             5,             'Fri to next Fri'             union all
    select date '2026-09-28',               date '2026-09-25',             0,             'end before start'

)

select
    label,
    expected,
    {{ business_days_between('start_date', 'end_date') }} as actual

from examples
where {{ business_days_between('start_date', 'end_date') }} != expected
