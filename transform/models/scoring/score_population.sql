-- Scoring: the population each check examines, from the table in
-- inventory/scoring_method.md. One row per check per entity.
-- It is the denominator for the false-positive rate: everything the check
-- looked at, whether or not it flagged it.

-- 1. Accounts of anyone with a termination date
select 'leaver_active_account' as check_name, accounts.account_id as entity_key
from {{ ref('int_accounts') }} as accounts
join {{ ref('int_employees') }} as employees
    on employees.employee_hash = accounts.employee_hash
where employees.termination_date is not null

union all

-- 2. Privileged grants open on the as-of date or made in the review period
select 'privileged_without_approval', grant_id
from {{ ref('int_grants') }}
where is_privileged
  and (is_open or granted_date between date('{{ var("review_start") }}') and date('{{ var("as_of_date") }}'))

union all

-- 3. People who held at least one grant with an SoD function during the review
--    period (held from granted_date up to, but not including, held_until)
select distinct 'sod_conflict', employee_hash
from {{ ref('int_grants') }}
where sod_function is not null
  and granted_date <= date('{{ var("as_of_date") }}')
  and held_until    > date('{{ var("review_start") }}')

union all

-- 4. Active accounts at least 30 days old with an open privileged grant
select distinct 'dormant_privileged_account', accounts.account_id
from {{ ref('int_accounts') }} as accounts
join {{ ref('int_grants') }} as grants
    on grants.account_id = accounts.account_id
where accounts.status = 'active'
  and date_diff(date('{{ var("as_of_date") }}'), accounts.created_date, day) >= 30
  and grants.is_open
  and grants.is_privileged

union all

-- 5. Grants made before a current employee's latest move
select 'access_not_removed_after_move', grants.grant_id
from {{ ref('int_grants') }} as grants
join {{ ref('int_employees') }} as employees
    on employees.employee_hash = grants.employee_hash
where employees.is_employed
  and grants.granted_date < employees.last_move_date

union all

-- 6. All invoices
select 'duplicate_invoice', invoice_id
from {{ ref('stg_invoices') }}

union all

-- 7. POs at or below the approval limit
select 'split_purchase', po_id
from {{ ref('stg_purchase_orders') }}
where amount <= {{ var('approval_limit') }}

union all

-- 8. All vendors
select 'vendor_bank_matches_employee', vendor_id
from {{ ref('stg_vendors') }}

union all

-- 9. Vendors created in the review period
select 'vendor_created_and_paid_same_day', vendor_id
from {{ ref('stg_vendors') }}
where created_date >= date('{{ var("review_start") }}')

union all

-- 10. All payments
select 'payment_without_invoice', payment_id
from {{ ref('stg_payments') }}
