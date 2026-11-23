-- Scoring: accuracy per check against the answer key. One row per check.
-- Definitions: inventory/scoring_method.md. Rates are left empty where the
-- denominator is zero (e.g. no look-alikes for that check), never shown as 0.

with results as (

    select * from {{ ref('score_case_results') }}

),

counts as (

    select
        check_name,
        countif(in_population)                    as population,
        countif(is_flagged)                       as flagged,
        countif(case_type = 'seeded_issue')       as seeded_issues,
        countif(case_type = 'look_alike')         as look_alikes,
        countif(outcome = 'TP')                   as tp,
        countif(outcome = 'FN')                   as fn,
        countif(outcome = 'FP (look-alike)')      as fp_look_alike,
        countif(outcome = 'FP (other)')           as fp_other,
        countif(outcome like 'TN%')               as tn,
        -- Planted issues the check could never flag, because they sit outside
        -- the population it examines. Already counted in fn.
        countif(case_type = 'seeded_issue' and not in_population) as fn_outside_population

    from results
    group by check_name

)

select
    check_name,
    population,
    flagged,
    seeded_issues,
    look_alikes,
    tp,
    fn,
    fn_outside_population,
    fp_look_alike + fp_other                                            as fp,
    fp_look_alike,
    fp_other,
    tn,

    -- safe_divide returns NULL instead of failing when dividing by zero.
    round(safe_divide(tp, tp + fp_look_alike + fp_other), 3)            as precision,
    round(safe_divide(tp, tp + fn), 3)                                  as recall,
    round(safe_divide(fp_look_alike + fp_other,
                      fp_look_alike + fp_other + tn), 4)                as false_positive_rate,
    round(safe_divide(fp_look_alike, look_alikes), 3)                   as look_alike_fp_rate

from counts
order by check_name
