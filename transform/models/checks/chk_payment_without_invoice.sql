-- Check 10: payment with no matching invoice. One row per payment.
-- Rule: inventory/check_rules.md, section 10.
--
-- Critical: no invoice ID, an invoice ID that doesn't exist, or an invoice from
-- a different vendor. The whole payment is unsupported.
-- High: overpayment. Payments on an invoice are taken in order (payment date,
-- then payment ID). Once the running total is more than the invoice amount plus
-- the rounding tolerance, that payment and every later one are flagged. The
-- payment that crosses the line reports only the excess; later ones their full amount.
-- Paying less than the invoice is not an exception.
-- Not testable on this data: cancelled or reversed invoices.

with payments as (

    select * from {{ ref('stg_payments') }}

),

invoices as (

    select * from {{ ref('stg_invoices') }}

),

joined as (

    select
        payments.payment_id,
        payments.vendor_id,
        payments.invoice_id,
        payments.payment_date,
        payments.amount,
        invoices.invoice_id is not null as invoice_exists,
        invoices.vendor_id              as invoice_vendor_id,
        invoices.amount                 as invoice_amount,

        -- Running total paid against this invoice, up to and including this payment.
        sum(payments.amount) over (
            partition by payments.invoice_id
            order by payments.payment_date, payments.payment_id
            rows between unbounded preceding and current row
        ) as running_total_paid

    from payments
    -- Left join: payments whose invoice can't be found must stay in.
    left join invoices
        on invoices.invoice_id = payments.invoice_id

),

tested as (

    select
        joined.*,
        invoice_id is null                                     as has_no_invoice_id,
        invoice_id is not null and not invoice_exists          as invoice_not_found,
        coalesce(invoice_vendor_id != vendor_id, false)        as invoice_for_other_vendor,
        coalesce(
            running_total_paid > invoice_amount + {{ var('rounding_tolerance') }},
            false
        )                                                      as is_overpayment

    from joined

)

select
    payment_id,
    vendor_id,
    invoice_id,
    payment_date,
    amount,
    invoice_vendor_id,
    invoice_amount,
    running_total_paid,

    array_to_string([
        if(has_no_invoice_id,        'no invoice ID',                    null),
        if(invoice_not_found,        'invoice ID not in the invoice data', null),
        if(invoice_for_other_vendor, 'invoice belongs to another vendor', null),
        if(is_overpayment,           'paid more than the invoice amount', null)
    ], '; ') as failure_reasons,

    -- How much of this payment has no invoice behind it. For the payment that
    -- crosses the invoice amount, that's the excess. For later payments the
    -- running total was already over, so least() gives the full amount.
    case
        when has_no_invoice_id or invoice_not_found or invoice_for_other_vendor then amount
        else least(amount, running_total_paid - invoice_amount)
    end as unsupported_amount,

    case
        when has_no_invoice_id or invoice_not_found or invoice_for_other_vendor then 'Critical'
        else 'High'
    end as severity

from tested
where has_no_invoice_id
   or invoice_not_found
   or invoice_for_other_vendor
   or is_overpayment
