-- Custom test for the tidy_invoice_number macro: worked examples with known
-- answers. Returns the examples the macro gets wrong; zero rows means pass.

with examples as (

    select 'INV-0045-01' as raw_number, 'INV451'  as expected union all   -- the rule book's example
    select 'INV-45-1',                  'INV451'                union all   -- ...and its match
    select 'inv 45/1',                  'INV451'                union all   -- lower case, space, slash
    select 'INV.0045.01',               'INV451'                union all   -- dots
    select '000123',                    '123'                   union all   -- zeros at the very start
    select 'INV-000',                   'INV0'                  union all   -- a run of only zeros keeps one
    select 'INV-1050',                  'INV1050'               union all   -- zeros inside a number stay
    select 'AB-0012',                   'AB12'                              -- a different prefix stays different

)

select
    raw_number,
    expected,
    {{ tidy_invoice_number('raw_number') }} as actual

from examples
where {{ tidy_invoice_number('raw_number') }} != expected
