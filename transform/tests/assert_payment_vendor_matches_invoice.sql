-- Custom (singular) test: a payment must go to the vendor whose invoice it pays.
-- Returns the payments breaking the rule; zero rows means pass.
-- Payments with no invoice are skipped here: they are a finding for the
-- payment_without_invoice check, not a data-integrity error.
--
-- Severity warn: a payment against another vendor's invoice is also a Critical
-- finding in check 10. As an error, this test would stop the build and skip
-- check 10, so the payment would only show up in the build log. As a warning,
-- the build carries on and check 10 reports it.

{{ config(severity = 'warn') }}

select
    p.payment_id,
    p.vendor_id as payment_vendor_id,
    i.vendor_id as invoice_vendor_id

from {{ ref('stg_payments') }} as p
join {{ ref('stg_invoices') }} as i
    on p.invoice_id = i.invoice_id

where p.vendor_id != i.vendor_id
