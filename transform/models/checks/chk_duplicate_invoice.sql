-- Check 6: duplicate invoice. One row per suspected duplicate: the later
-- invoice of each matching pair.
-- Rule: inventory/check_rules.md, section 6.
--
-- Two invoices from the same vendor match if:
--   Tier 1 (exact)          same tidied number, same amount
--   Tier 2 (same number)    same tidied number, different amount
--   Tier 3 (re-keyed)       different number, same amount, dates within 7 days
-- Invoices are ordered by invoice date, then invoice ID. Each later invoice
-- appears once, paired with its earliest match at the strongest tier it reaches.
-- Severity comes from payment status: both paid Critical, one paid High,
-- neither paid Medium.
-- Not testable on this data: cancelled or reversed invoices and credit notes.

with invoices as (

    select * from {{ ref('int_invoices') }}

),

-- Every pair of invoices from the same vendor where the second comes later in
-- the ordering, and the two match on one of the tiers.
matches as (

    select
        later.invoice_id,
        earlier.invoice_id   as matched_invoice_id,
        earlier.invoice_date as matched_invoice_date,
        case
            when later.invoice_number_tidy = earlier.invoice_number_tidy
             and later.amount = earlier.amount                               then 1
            when later.invoice_number_tidy = earlier.invoice_number_tidy     then 2
            else 3
        end as tier

    from invoices as later
    join invoices as earlier
        on  earlier.vendor_id = later.vendor_id
        and (
            earlier.invoice_date < later.invoice_date
            or (earlier.invoice_date = later.invoice_date and earlier.invoice_id < later.invoice_id)
        )

    where later.invoice_number_tidy = earlier.invoice_number_tidy          -- tiers 1 and 2: no date window
       or (
            later.amount = earlier.amount                                    -- tier 3
            and date_diff(later.invoice_date, earlier.invoice_date, day) <= 7
       )

),

-- Keep one match per later invoice: the strongest tier (1 before 2 before 3),
-- then the earliest invoice at that tier.
best_match as (

    select *
    from matches
    qualify row_number() over (
        partition by invoice_id
        order by tier, matched_invoice_date, matched_invoice_id
    ) = 1

)

select
    later.invoice_id,
    later.vendor_id,
    later.vendor_invoice_number,
    later.invoice_date,
    later.amount,
    later.is_paid,

    earlier.invoice_id            as matched_invoice_id,
    earlier.vendor_invoice_number as matched_vendor_invoice_number,
    earlier.invoice_date          as matched_invoice_date,
    earlier.amount                as matched_amount,
    earlier.is_paid               as matched_is_paid,

    best_match.tier,
    case best_match.tier
        when 1 then 'Exact'
        when 2 then 'Same number, different amount'
        when 3 then 'Re-keyed'
    end                                                          as tier_label,
    date_diff(later.invoice_date, earlier.invoice_date, day)     as days_apart,

    case
        when later.is_paid and earlier.is_paid then 'Critical'   -- recover from the vendor
        when later.is_paid or  earlier.is_paid then 'High'       -- block the open one
        else 'Medium'                                            -- cancel before the next run
    end                                                          as severity

from best_match
join invoices as later
    on later.invoice_id = best_match.invoice_id
join invoices as earlier
    on earlier.invoice_id = best_match.matched_invoice_id
