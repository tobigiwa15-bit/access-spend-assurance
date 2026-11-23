-- Check 8: vendor bank account matches an employee's. One row per vendor.
-- Rule: inventory/check_rules.md, section 8.
--
-- Vendors and employees are compared on bank_account_hash. Both are hashed with
-- the same keyed macro, so equal hashes mean equal account numbers, without
-- anyone seeing a number. Current employees and leavers are both compared.
-- "Employed" on a date means inside one of the person's employment periods,
-- so a payment in the gap between leaving and a rehire counts as to a leaver.
-- Severity:
--   Critical  paid while the person was employed, or they created or approved the vendor
--   High      current employee and not yet paid; or a leaver, and the vendor was
--             created or paid while they were employed
--   Medium    a leaver, and the vendor was created after they left
-- Not testable on this data: vendor status (every vendor is in scope) and
-- conflict-of-interest declarations (none are on record).

with matched as (

    select
        vendors.vendor_id,
        vendors.vendor_name,
        vendors.bank_account_masked,
        vendors.created_date,
        vendors.created_by_hash,
        vendors.approved_by_hash,
        employees.employee_hash,
        employees.is_employed       as is_current_employee

    from {{ ref('stg_vendors') }} as vendors
    join {{ ref('stg_employees') }} as staff
        on staff.bank_account_hash = vendors.bank_account_hash
    join {{ ref('int_employees') }} as employees
        on employees.employee_hash = staff.employee_hash

),

periods as (

    select * from {{ ref('int_employment_periods') }}

),

-- Payments to the matched vendors only.
matched_payments as (

    select payments.*
    from {{ ref('stg_payments') }} as payments
    join matched
        on matched.vendor_id = payments.vendor_id

),

payment_totals as (

    select
        vendor_id,
        count(*)    as payment_count,
        sum(amount) as total_paid
    from matched_payments
    group by vendor_id

),

-- Vendors paid on a day the matched person was employed (inside a period;
-- last_day is inclusive and empty while the period is ongoing).
paid_while_employed as (

    select distinct matched_payments.vendor_id
    from matched_payments
    join matched
        on matched.vendor_id = matched_payments.vendor_id
    join periods
        on  periods.employee_hash = matched.employee_hash
        and matched_payments.payment_date >= periods.start_date
        and (periods.last_day is null or matched_payments.payment_date <= periods.last_day)

),

created_while_employed as (

    select distinct matched.vendor_id
    from matched
    join periods
        on  periods.employee_hash = matched.employee_hash
        and matched.created_date >= periods.start_date
        and (periods.last_day is null or matched.created_date <= periods.last_day)

),

assessed as (

    select
        matched.*,
        coalesce(payment_totals.payment_count, 0)          as payment_count,
        coalesce(payment_totals.total_paid, 0)             as total_paid,
        paid.vendor_id is not null                         as paid_while_employed,
        created.vendor_id is not null                      as created_while_employed,
        coalesce(matched.created_by_hash  = matched.employee_hash, false) as person_created_vendor,
        coalesce(matched.approved_by_hash = matched.employee_hash, false) as person_approved_vendor

    from matched
    left join payment_totals
        on payment_totals.vendor_id = matched.vendor_id
    left join paid_while_employed as paid
        on paid.vendor_id = matched.vendor_id
    left join created_while_employed as created
        on created.vendor_id = matched.vendor_id

)

select
    vendor_id,
    vendor_name,
    bank_account_masked,
    employee_hash,
    is_current_employee,
    created_date,
    person_created_vendor,
    person_approved_vendor,
    created_while_employed,
    paid_while_employed,
    payment_count,
    total_paid,

    case
        when paid_while_employed
          or person_created_vendor
          or person_approved_vendor                         then 'Critical'
        -- Current employee, not paid while employed. Normally "not yet paid";
        -- the rare case of payments only from before they were hired lands here too.
        when is_current_employee                            then 'High'
        -- Leaver, created while employed. ("Paid while employed" is already Critical.)
        when created_while_employed                         then 'High'
        else 'Medium'                                       -- leaver; created after they left
    end as severity

from assessed
