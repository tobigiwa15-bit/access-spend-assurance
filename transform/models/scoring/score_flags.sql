-- Scoring: every row flagged by every check, stacked into one list.
-- One row per check per flagged entity.
--
-- Each check has its own columns, so only the two things scoring needs are
-- kept: which check, and the entity at its output grain. Severity is left out
-- on purpose: scoring only asks whether a row was flagged.

select 'leaver_active_account'            as check_name, account_id    as entity_key from {{ ref('chk_leaver_active_account') }}            union all
select 'privileged_without_approval',                    grant_id                    from {{ ref('chk_privileged_without_approval') }}      union all
select 'sod_conflict',                                   employee_hash               from {{ ref('chk_sod_conflict') }}                     union all
select 'dormant_privileged_account',                     account_id                  from {{ ref('chk_dormant_privileged_account') }}       union all
select 'access_not_removed_after_move',                  grant_id                    from {{ ref('chk_access_not_removed_after_move') }}    union all
select 'duplicate_invoice',                              invoice_id                  from {{ ref('chk_duplicate_invoice') }}                union all
select 'split_purchase',                                 po_id                       from {{ ref('chk_split_purchase') }}                   union all
select 'vendor_bank_matches_employee',                   vendor_id                   from {{ ref('chk_vendor_bank_matches_employee') }}     union all
select 'vendor_created_and_paid_same_day',               vendor_id                   from {{ ref('chk_vendor_created_and_paid_same_day') }} union all
select 'payment_without_invoice',                        payment_id                  from {{ ref('chk_payment_without_invoice') }}
