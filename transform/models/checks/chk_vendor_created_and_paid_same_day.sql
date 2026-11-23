-- Check 9: vendor created and paid too quickly. One row per vendor.
-- Rule: inventory/check_rules.md, section 9. (The name keeps the plan's
-- "same day" wording; the rule widens it to 3 business days.)
--
-- A vendor is flagged if its first payment is within 3 business days of the
-- vendor's creation date (not its approval date).
--   Critical  paid on the day it was created, or paid before it was approved
--   High      paid 1 to 3 business days after creation
-- The finding reports every payment inside the window and their total.
-- Not testable on this data: vendors created before the review period, because
-- payment data starts then and their real first payment can't be seen.

with vendors as (

    select * from {{ ref('stg_vendors') }}
    where created_date >= date('{{ var("review_start") }}')

),

-- Each payment with how many business days after the vendor's creation it was.
vendor_payments as (

    select
        payments.vendor_id,
        payments.payment_id,
        payments.payment_date,
        payments.amount,
        {{ business_days_between('vendors.created_date', 'payments.payment_date') }} as business_days_after_creation

    from {{ ref('stg_payments') }} as payments
    join vendors
        on vendors.vendor_id = payments.vendor_id

),

first_payment as (

    select *
    from vendor_payments
    qualify row_number() over (
        partition by vendor_id
        order by payment_date, payment_id
    ) = 1

),

window_payments as (

    select
        vendor_id,
        count(*)    as payments_in_window,
        sum(amount) as amount_in_window
    from vendor_payments
    where business_days_after_creation <= 3
    group by vendor_id

)

select
    vendors.vendor_id,
    vendors.vendor_name,
    vendors.created_date,
    vendors.approved_date,                            -- reported, not used for the window
    first_payment.payment_date                        as first_payment_date,
    first_payment.business_days_after_creation        as business_days_to_first_payment,
    first_payment.payment_date < vendors.approved_date as paid_before_approval,
    window_payments.payments_in_window,
    window_payments.amount_in_window,

    case
        when first_payment.payment_date <= vendors.created_date      -- same day (or, oddly, earlier)
          or first_payment.payment_date <  vendors.approved_date then 'Critical'
        else 'High'
    end as severity

from first_payment
join vendors
    on vendors.vendor_id = first_payment.vendor_id
join window_payments
    on window_payments.vendor_id = first_payment.vendor_id

-- The first payment must be inside the window. (The macro gives 0 for a payment
-- on or before the creation date, so those count as inside it.)
where first_payment.business_days_after_creation <= 3
