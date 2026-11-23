-- Check 7: split purchase. One row per PO, for every PO in a suspected split.
-- Rule: inventory/check_rules.md, section 7.
--
-- L is the approval limit (var approval_limit): the most a lower approver may
-- approve. POs above L are set aside first: they went to the higher approver
-- anyway. A 7-day window starts at each remaining PO and takes in the POs with
-- the same vendor and requester dated within the next 6 days. A window is a
-- suspected split when its total is above L (every PO in it is already <= L).
-- A PO is flagged if any window containing it qualifies.
-- High if the same approver approved every PO, or every PO is within 10% below
-- L, or all were raised on the same day. Otherwise Medium.
-- Not testable on this data: cancelled POs, and more than one approval level
-- (this data has one limit, so the test runs once, against it).

with pos as (

    select * from {{ ref('stg_purchase_orders') }}
    where amount <= {{ var('approval_limit') }}

),

-- Each PO starts a window. Its members: same vendor, same requester, dated
-- from the starting PO's date to 6 days later (7 days in all).
window_members as (

    select
        starting_po.po_id   as window_id,
        starting_po.po_date as window_start,
        member.po_id,
        member.po_date,
        member.amount,
        member.approved_by_hash

    from pos as starting_po
    join pos as member
        on  member.vendor_id         = starting_po.vendor_id
        and member.requested_by_hash = starting_po.requested_by_hash
        and member.po_date between starting_po.po_date
                               and date_add(starting_po.po_date, interval 6 day)

),

-- One row per window that qualifies, with the facts severity needs.
split_windows as (

    select
        window_id,
        window_start,
        count(*)                          as group_po_count,
        sum(amount)                       as group_total,
        count(distinct approved_by_hash)  as approver_count,
        countif(approved_by_hash is null) as pos_without_approver,
        min(amount)                       as smallest_amount,
        count(distinct po_date)           as days_used

    from window_members
    group by window_id, window_start
    having sum(amount) > {{ var('approval_limit') }}

),

rated as (

    select
        split_windows.*,
        array_to_string([
            if(approver_count = 1 and pos_without_approver = 0, 'same approver for every PO', null),
            if(smallest_amount >= 0.9 * {{ var('approval_limit') }}, 'every PO within 10% below the limit', null),
            if(days_used = 1, 'all raised on the same day', null)
        ], '; ') as high_reasons

    from split_windows

),

-- A PO can sit in more than one qualifying window. Keep the one that rates it
-- highest (shared definition: the highest severity wins), then the largest total.
po_best_window as (

    select
        window_members.po_id,
        rated.window_id,
        rated.window_start,
        rated.group_po_count,
        rated.group_total,
        rated.high_reasons

    from window_members
    join rated
        on rated.window_id = window_members.window_id
    qualify row_number() over (
        partition by window_members.po_id
        order by (rated.high_reasons != '') desc, rated.group_total desc, rated.window_start
    ) = 1

)

select
    pos.po_id,
    pos.vendor_id,
    pos.requested_by_hash,
    pos.approved_by_hash,
    pos.po_date,
    pos.amount,
    po_best_window.window_start                  as group_window_start,
    po_best_window.group_po_count,
    po_best_window.group_total,
    {{ var('approval_limit') }}                  as approval_limit,
    nullif(po_best_window.high_reasons, '')      as high_reasons,
    case when po_best_window.high_reasons != '' then 'High' else 'Medium' end as severity

from po_best_window
join pos
    on pos.po_id = po_best_window.po_id
