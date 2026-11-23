# Scoring method

How each check in `check_rules.md` is measured against the answer key. Like the rules, this was agreed **before** any score was seen, so the definitions can't be chosen to flatter the results.

## The answer key

`generate/plant_issues.py` plants each issue and look-alike in the synthetic data and records it in `answer_key.csv`, one row per case:

- **seeded_issue:** a planted control failure the check should flag.
- **look_alike:** a legitimate case built to resemble an issue, which the check should not flag. There are look-alikes for check 1 (rehired leavers), check 2 (emergency grants approved after the fact) and check 6 (recurring fixed-fee invoices).

Each case names one entity at the check's output grain (an account, a grant, a person and so on), so it can be matched to the check's rows exactly.

## Measures

Every item in a check's population falls into one box:

| | Seeded issue | Not a seeded issue |
|---|---|---|
| **Flagged** | true positive (TP) | false positive (FP) |
| **Not flagged** | false negative (FN) | true negative (TN) |

- **Precision** = TP / (TP + FP): when the check flags something, how often it is a planted issue.
- **Recall** = TP / (TP + FN): how many planted issues the check finds.
- **False-positive rate** = FP / (FP + TN): how many items that aren't planted issues it flags.
- **Look-alike false-positive rate** = look-alikes flagged / look-alikes: the honest test. Seeded issues were planted to match the checks, so recall on them is expected to be high. Look-alikes test whether a check can tell an issue from something that only resembles one.

Severity plays no part. A row is either flagged or it isn't.

## Population (the false-positive-rate denominator)

The population for each check is its own scope from the rule book: the items it examines before applying its test. Dividing by everything in the data instead (all accounts, say) would make any check look nearly perfect.

| Check | Population |
|---|---|
| 1. Leaver with active account | Accounts of anyone with a termination date |
| 2. Privileged access without approval | Privileged grants open on the as-of date or made in the review period |
| 3. SoD conflict | People who held at least one grant with an SoD function during the review period |
| 4. Dormant privileged account | Active accounts at least 30 days old with an open privileged grant |
| 5. Access not removed after move | Grants made before a current employee's latest move |
| 6. Duplicate invoice | All invoices |
| 7. Split purchase | POs at or below the approval limit |
| 8. Vendor bank matches employee | All vendors |
| 9. Vendor created and paid quickly | Vendors created in the review period |
| 10. Payment without invoice | All payments |

## False positives

Every flagged item that is not a seeded issue counts as a false positive, and two kinds are reported separately:

- **Look-alike false positives:** legitimate cases built to resemble issues.
- **Other false positives:** items that were neither planted nor look-alikes.

When false positives are reviewed, each kind is given a cause, such as: the rule is stricter than the company's normal process, a bug in the SQL, or a gap in the data. A rule is only changed to fix a genuine bug, and the change is logged in `check_rules.md` with the scores before and after. A strict rule that flags what the data treats as normal is not a bug. It is a finding about the rule and is reported as one.

## Where it runs, and who can see it

Scoring runs in dbt (`transform/models/scoring/`) and builds the `asa_scoring` dataset. Employee IDs in the answer key, including any inside its descriptions, are replaced with the same keyed hash used everywhere else, so scoring never handles a raw ID. `results/accuracy_by_check.csv` is written from the final scoring table by a script in this repo, so every figure can be rerun.

`asa_scoring` holds the answer key, so it is kept apart from the data the investigation agent reads. The agent's read-only account is granted the staging, intermediate and checks datasets only. It is never granted `asa_scoring` or `asa_raw`.

## Changes to the test data

The rules are never changed to improve a score. The test data may be corrected when it is unrealistic, but only with the scores from before the change kept here.

### 2026-11-23: planted transactions dated before their vendor existed

**Found by:** reviewing check 9's two "other" false positives in the first scoring run.

**Defect:** `plant_issues.py` chose a vendor and a date for planted split purchases and planted no-invoice payments without checking that the vendor existed on that date. Three vendors had POs, invoices or payments dated before their creation date: V0434 and V0495 (split purchases), and V0471 (a no-invoice payment six months before the vendor was created). No real ERP allows that. Check 9 flagged V0434 and V0471 correctly for what the data showed, but the answer key, reasonably, did not list them.

**Fix:** planted split purchases and no-invoice payments now only use a vendor from 14 days after its approval, the same first-use rule the clean data follows (`VENDOR_FIRST_USE_DAYS`). The data was regenerated and every check rescored. The causes of the other ten misses and false positives were not touched.

**Scores before the fix** (first scoring run):

| Check | Population | Flagged | TP | FN | FP look-alike | FP other | Precision | Recall | FPR | Look-alike FPR |
|---|---|---|---|---|---|---|---|---|---|---|
| access_not_removed_after_move | 305 | 10 | 10 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |
| dormant_privileged_account | 78 | 6 | 6 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |
| duplicate_invoice | 4853 | 8 | 8 | 2 | 0 | 0 | 1.000 | 0.8 | 0.000 | 0.00 |
| leaver_active_account | 350 | 16 | 10 | 0 | 2 | 4 | 0.625 | 1.0 | 0.018 | 0.10 |
| payment_without_invoice | 4656 | 8 | 8 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |
| privileged_without_approval | 90 | 10 | 8 | 0 | 2 | 0 | 0.800 | 1.0 | 0.024 | 0.25 |
| sod_conflict | 1497 | 10 | 10 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |
| split_purchase | 3278 | 19 | 19 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |
| vendor_bank_matches_employee | 506 | 6 | 6 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |
| vendor_created_and_paid_same_day | 97 | 8 | 6 | 0 | 0 | 2 | 0.750 | 1.0 | 0.022 | n/a |

**Scores after the fix** (data regenerated, reloaded, rebuilt and rescored):

| Check | Population | Flagged | TP | FN | FP look-alike | FP other | Precision | Recall | FPR | Look-alike FPR |
|---|---|---|---|---|---|---|---|---|---|---|
| access_not_removed_after_move | 305 | 10 | 10 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |
| dormant_privileged_account | 78 | 6 | 6 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |
| duplicate_invoice | 4854 | 8 | 8 | 2 | 0 | 0 | 1.000 | 0.8 | 0.000 | 0.00 |
| leaver_active_account | 350 | 16 | 10 | 0 | 2 | 4 | 0.625 | 1.0 | 0.018 | 0.10 |
| payment_without_invoice | 4657 | 8 | 8 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |
| privileged_without_approval | 90 | 10 | 8 | 0 | 2 | 0 | 0.800 | 1.0 | 0.024 | 0.25 |
| sod_conflict | 1497 | 10 | 10 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |
| split_purchase | 3279 | 20 | 20 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |
| vendor_bank_matches_employee | 506 | 6 | 6 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |
| vendor_created_and_paid_same_day | 97 | 6 | 6 | 0 | 0 | 0 | 1.000 | 1.0 | 0.000 | n/a |

**What changed:** check 9's two false positives are gone, and it now flags exactly its 6 planted vendors. The access data is byte-identical, so checks 1 to 5 give exactly the same results. Spend planting drew partly new cases after the fix: split purchases now have 20 planted POs instead of 19 (one set has three parts), so the answer key has 152 cases. Check 6 still misses the same two re-keyed duplicates. Their invoice IDs were renumbered (now INV02308 and INV03859), but they are the same pairs: same vendors and dates, 19 and 13 days apart, same PO.

**Causes of the other ten, recorded before the fix:**
- Check 1, 4 other FPs: privileged accounts disabled 2 days after the leaving date. The rule gives privileged accounts no grace; the company's process allows 0 to 2 days for every leaver. The rule is stricter than the process.
- Check 1, 2 look-alike FPs: rehired Team Leads who came back as contractors with a staff role. The roster still shows "Team Lead", because HR doesn't record a rehire's new level, so their access is judged against the lead's entitlements. A gap in the data.
- Check 2, 2 look-alike FPs: emergency grants approved 2 business days after the grant. The rule requires T+1; the company treats up to 2 days as acceptable. The rule is stricter than the process.
- Check 6, 2 misses: re-entries with a letter added to the invoice number, same amount and same PO, entered 13 and 19 days after the original. This is outside Tier 3's 7-day window, a deliberate trade-off that kept all 30 recurring look-alikes unflagged. A known limit of the rule. Both pairs share the same PO, a signal the rule doesn't use.
