-- Intermediate: every invoice with its tidied number and what has been paid
-- against it. One row per invoice.
--
-- Used by check 6 (duplicates, and whether each one was paid) and check 10
-- (payments compared with the invoice they claim to pay).

with invoices as (

    select * from {{ ref('stg_invoices') }}

),

paid as (

    select
        invoice_id,
        count(*)    as payment_count,
        sum(amount) as total_paid
    from {{ ref('stg_payments') }}
    where invoice_id is not null      -- payments with no invoice belong to check 10
    group by invoice_id

)

select
    invoices.invoice_id,
    invoices.vendor_id,
    invoices.po_id,
    invoices.vendor_invoice_number,
    {{ tidy_invoice_number('invoices.vendor_invoice_number') }} as invoice_number_tidy,
    invoices.invoice_date,
    invoices.amount,
    invoices.entered_by_hash,
    coalesce(paid.payment_count, 0) as payment_count,
    coalesce(paid.total_paid, 0)    as total_paid,
    paid.invoice_id is not null     as is_paid     -- at least one payment linked (rule book, check 6)

from invoices
-- Left join: unpaid invoices stay in. They matter to check 6's severity.
left join paid
    on invoices.invoice_id = paid.invoice_id
