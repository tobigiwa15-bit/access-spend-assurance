-- Custom (singular) test: an invoice must be from the same vendor as the PO it bills.
--
-- A singular test is a query that returns the rows breaking a rule. Zero rows
-- means pass, just like an ACL exception script. Generic tests can't express
-- this one, because it compares columns across two tables.
--
-- It is a data-integrity rule, not an audit check: a mismatch would mean the
-- links between tables are broken, so nothing built on them can be trusted.

select
    i.invoice_id,
    i.vendor_id  as invoice_vendor_id,
    po.vendor_id as po_vendor_id

from {{ ref('stg_invoices') }} as i
join {{ ref('stg_purchase_orders') }} as po
    on i.po_id = po.po_id

where i.vendor_id != po.vendor_id
