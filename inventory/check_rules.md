# Check rules

The rule for each check, written in plain English **before** any SQL was written or any result was seen. The dbt models in `transform/models/checks/` implement these rules exactly. Phase 3 measures them against the answer key.

Why first: every check involves judgement calls (a grace period, a time window, what counts as approved). Deciding them after seeing the scores would mean choosing whichever rule scores best, which makes the accuracy figures meaningless. If a rule turns out to be genuinely wrong, it is changed openly and logged in the change log at the bottom, with the scores before and after.

## Facts every rule can rely on

- **As-of date:** 30 September 2026. "Today" for every check.
- **Review period:** 1 October 2024 to 30 September 2026, for both spend and access. Payment, invoice and PO data only exist for this period.
- **Login history:** only the last 90 days (3 July to 30 September 2026). An account with no login in that window has no known last login.
- **PO approval threshold:** 5,000,000. Up to it, a Procurement team lead can approve; above it, the Head of Procurement.
- **Privileged** means an administrator role (`is_privileged` is true in `stg_roles`).
- **Output grain is fixed** for each check (one row per account, grant, person and so on, as stated below), so results can be matched to the answer key. The rule decides *which* rows appear, not what a row is.
- All people appear as keyed hashes. The checks never see names or account numbers.

## Shared definitions

- **Business day:** Monday to Friday. There are no public holidays, because the data has no holiday calendar. Counting starts the day after the start date. For example, from a Friday, the following Monday is 1 business day later.
- **Held:** a grant is held from its grant date up to, but not including, its revoke date. The revoke date is the first day the access is no longer held. A grant with no revoke date is held up to and including the as-of date.
- **Account active:** an account works from its created date up to, but not including, its disabled date. The disabled date is the first day the account no longer works, the same convention as a grant's revoke date. An account still active on the as-of date last worked on the as-of date.
- **Entitled role:** a role is in the role matrix for a person's department and level. Two allowances follow from how the matrix is written. Where a department has no "head" rows (every department except Procurement), a head is entitled to that department's lead roles. The IT "admin" roles count as entitled for anyone currently in IT (see the known limit under check 5). Checks 1 and 5 both use this definition.
- **Level:** taken from the job title, matched case-insensitively. "Head of …" and "Acting Head of …" mean head, because an acting head holds the head's authority. "Deputy Head …" and "Team Lead" mean lead. Any other title means staff. The current data only has "Head of …", "Team Lead" and staff titles.
- **Severity:** when more than one severity condition applies, the highest wins.
- **Severity and scoring:** Phase 3 scores whether a row appears, not its severity. Severity only affects how findings are ranked for review.
- **"Not testable on this data"** marks a part of a rule that needs information the synthetic data doesn't contain. That part is left out of the model, and it is listed as a known limit in the inventory. The data was not changed to fit the rules.

## How to fill this in

For each check, answer the questions under **Decide**, then write the rule as you would in an audit programme: one to three sentences someone else could implement without asking you anything. Add a line of reasoning under **Why**. There are no right answers here, only defensible ones.

---

## 1. Leaver with active account

**Purpose:** find people who have left but can still get into a system.
**Output:** one row per account.
**Data:** `stg_employees` (termination_date), `stg_accounts` (status, disabled_date), `stg_hr_events`, `stg_logins`.

**Decide:**
- How many days after the termination date before an active account counts as an exception (grace period)?
- Is every leaver with an active account flagged, or do later HR events change that?
- Do logins after the termination date matter to whether it's flagged, or only to how serious it is?

**Rule:**
- An account counts as an exception if it is still active more than 1 business day after the termination date. For privileged accounts (admin, DBA, system and super-user roles), there is no grace period: the account is an exception if it is active at any point after the termination date. If HR records a termination after its effective date (a backdated termination), count the grace period from the later of the effective date and the date HR entered it. Report the late HR entry as a separate HR timeliness exception.
- Flag every leaver with an active account, except where a later HR event, dated on or before the test date, shows a valid ongoing engagement. These events are rehire, reversal of the termination, or conversion to contractor or consultant with an approved contract. The exclusion only applies if the account is tied to the new engagement and its access matches the new role. Otherwise, the account is still flagged
- Logins after the termination date do not decide whether an account is flagged. They only decide how serious it is:
    1) Critical: any successful login after the termination date, on any account
    2) High: a privileged account, or an account on a finance or payment system, is active with no logins
    3) Medium: a standard account is active beyond the grace period with no logins
Every Critical exception triggers a review of what the account did after termination.

**Agreed details:**
- Two kinds of exception are reported. **Open:** the account is still active on the as-of date, past the grace period. **Disabled late:** the account was disabled after the grace period ended. The report shows the number of days late.
- An account is privileged for the no-grace rule if it held an open privileged grant at any point from the termination date until it was disabled. For an account that is still active, that period runs to the as-of date. "Admin, DBA, system and super-user roles" means `is_privileged` in `stg_roles`. The only privileged roles in this data are the four administrator roles.
- "Finance or payment system" (the High tier) means core banking and the payments console.
- Rehire exclusion: each person keeps the same account in a system when rehired, so "tied to the new engagement" means the account belongs to the rehired person. "Access matches the new role" means every grant open on the as-of date is in the role matrix for the person's current department and level. The grants don't have to be dated on or after the rehire date.
- Logins only cover 3 July to 30 September 2026. "No logins" means no logins in that window, and a Critical rating can only come from a login in that window.

**Not testable on this data:**
- Backdated terminations and the HR timeliness exception. The HR data has an effective date but no date the termination was entered.
- The "reversal of the termination" and "conversion with an approved contract" exclusions. The only later HR event in the data is a rehire, and there are no contracts.

**Why:**
- HR and identity systems don't update instantly. A short grace period stops false exceptions caused by normal processing delay, so the report shows real failures. Privileged accounts get no allowance because one misused admin login can change data, create users or hide activity. The damage is far greater, so the risk can't be left open even for a day. IT can't disable an account it doesn't know about, so blaming access management for HR's delay would put the exception in the wrong place. Logging the late entry separately keeps the real cause visible. The account was still exposed during that gap, and someone has to own fixing it
- Some people really do come back or change status, and flagging them wastes review time and weakens trust in the report. The exclusion is narrow because "they came back" is also a common way to hide stale access. A rehired person who keeps their old role's access has the same problem as a leaver: access nobody has reviewed and nobody can justify.
- An active account is a risk even if nobody has used it. The credentials still work, and they could be shared, phished or reused. If only accounts with logins were flagged, the bank would find the problem only after it had already been exploited. Login activity is still the strongest sign that the risk has actually happened, so it raises the severity and adds an investigation step to check whether data or transactions were affected.


---

## 2. Privileged access without approval

**Purpose:** find administrator access granted without a valid approval.
**Output:** one row per grant.
**Data:** `stg_access_grants` (grant_type, approver_hash, approval_date, granted_date, revoked_date), `stg_roles`, `stg_accounts`, `stg_employees`.

**Decide:**
- Which grants are in scope: open ones only, all grants ever, or grants made within a period?
- What counts as approved: an approver on record? An approval dated on or before the grant? Within some days after it?
- Does the grant type (standard or emergency) change the rule?
- Is an approval by the person who received the access valid?

**Rule:**
- The test covers (a) every privileged grant that is open on the test date, whenever it was granted, and (b) every privileged grant made during the review period, including ones already removed
- A standard grant is approved only if all three of these are true:
    1) An approver is recorded against the specific grant.
    2) The approver has authority under the access approval matrix for that system and role.
    3) The approval is dated on or before the grant date.
If there is no approval, the exception is High. If the approval came after the grant, or the approver lacked authority, the exception is Medium.
- An emergency (break-glass) grant can be made before approval, but it is valid only if all three of these are true:
    1) It is recorded as an emergency.
    2) It is approved after the fact by an authorised approver by the end of the next business day after the grant (T+1).
    3) It is removed or expires within the maximum emergency window (3 days).
Missing any one of these makes it an exception, rated High.
- An approval is never valid if the approver is the person receiving the access. It is also not valid if the approver is the person who set up the access. Match people by staff ID, not by name, so that second accounts and proxy accounts are caught.

**Agreed details:**
- Scope (b) uses the review period, 1 October 2024 to 30 September 2026.
- A self-approval counts as no approval, so it is rated High.
- The 3-day emergency window is 3 calendar days: the revoke date is no more than 3 days after the grant date. An emergency grant still open more than 3 days after it was made fails condition 3.

**Not testable on this data:**
- The approver's authority (standard condition 2, emergency condition 2, and the Medium tier for an approver without authority). There is no access approval matrix. Only the approver's presence, timing and independence are tested.
- "The person who set up the access". The data doesn't record who carried out each grant.
- Expiry dates. Grants only have a revoke date, so "removed or expires" is tested on the revoke date alone.

**Why:**
- An open grant is a live risk however old it is. If the test only looked at the period, unapproved access from before the period would never be found. Grants that were made and removed within the period are included too, because short-lived admin access is a common way to make an unauthorised change and then cover the trail. A grant that no longer exists can still have done damage while it was active.
- An approval is a preventive control. Its job is to stop inappropriate access before it exists. An approval given after the access was granted is only a sign-off on something already done, so it can't prevent anything. Checking the approver's authority stops approvals from people who are reachable but not accountable for the system. The severity tiers separate access nobody approved from a process failure where someone did agree to it.
- Waiting for approval during a system outage can cost more than the access risk, so emergency access has to be allowed. That makes the emergency route the easiest way around the normal control, though. The conditions keep it narrow: there must be a stated reason, an accountable person must approve it quickly, and the time limit stops temporary access from quietly becoming permanent.
- The point of an approval is an independent check. Someone who approves their own access has only recorded their own request, so the grant is effectively unapproved. Separating the approver from the person who sets up the access stops one person from both authorising and carrying out the change. Matching by staff ID closes the gap where someone uses a second account to approve their own request.

---

## 3. Segregation-of-duties conflict

**Purpose:** find people who hold two functions that must be split, as listed in `stg_sod_rules`.
**Output:** one row per person.
**Data:** `stg_access_grants`, `stg_accounts`, `stg_roles` (sod_function), `stg_sod_rules`.

**Decide:**
- Is it based on access held on the as-of date, or on any time two conflicting roles overlapped?
- Do conflicts count across different systems, or only within one system?

**Rule:**
- A person is flagged if, through their grants, they hold both functions of any pair in stg_sod_rules. This is tested in two ways:
    1) Current conflict: both functions are held on the as-of date.
    2) Historical overlap: both functions were held at the same time for at least one day during the review period, but not on the as-of date.
A grant counts as held from its grant date up to, but not including, its revoke date (see "Held" above). If there is no revoke date, it counts as held until the as-of date. A role removed on the same day another is granted doesn't overlap with it. Each person's row shows whether the conflict is current, historical or both. A current conflict always ranks above a historical one.
- Test conflicts at person level, across all systems. Accounts with no linked person can't be tested. Report them as a separate data-quality exception, not as a pass.

**Agreed details:**
- The historical test uses the review period, 1 October 2024 to 30 September 2026.
- To rank current above historical, a person with any current conflict ("Current" or "Both") is rated High, and one with only historical conflicts is rated Medium.
- Unlinked accounts are caught by the staging tests: `not_null` and `relationships` on `stg_accounts.employee_hash`. If either test fails, the build stops before any check runs, so no separate model is needed.

**Why:**
- A current conflict is a live risk that someone needs to fix now. Testing only the as-of date, though, would miss someone who held both roles for a while, could have used them, and then lost one before the test date. That is exactly the window in which fraud happens. Showing historical overlaps separately means those periods can be checked for transactions that actually exploited the conflict, without mixing them into the list of things to remove today.
- SoD risk is about what a person can do, not what one system allows. Someone who can create a vendor in the ERP and release payments in the payment system can carry out the same fraud as someone who can do both in one place. Splitting the work across systems only makes it harder to see. Testing within a system only would miss the most dangerous conflicts, which tend to sit between finance and payment platforms. Unlinked accounts are reported because a conflict that can't be tested is not proof that there is no conflict.

---

## 4. Dormant privileged account

**Purpose:** find administrator accounts nobody is using, which are easy to misuse unnoticed.
**Output:** one row per account.
**Data:** `stg_accounts`, `stg_access_grants`, `stg_roles`, `stg_logins` (last 90 days only).

**Decide:**
- How many days without a login makes an account dormant? (Remember the login history covers 90 days.)
- Which accounts count as privileged: any account holding an open administrator grant?
- How should an account created more recently than your threshold be treated?

**Rule:**
- A privileged account is dormant if it has had no successful login in the 30 days before the as-of date. Only successful logins count. Failed attempts don't. If an account has no login anywhere in the 90-day history, report it as "No login in available history (90+ days)" and don't show a last-login date.
- An account is in scope if, on the as-of date, it is enabled and holds at least one open grant to a role marked as administrator or privileged in stg_roles. Disabled or locked accounts are out of scope.
- An account created less than 30 days before the as-of date is not tested for dormancy, because it hasn't existed long enough to fail. Once it is 30 days old, it is tested in the normal way, so an account never used since it was created will be flagged.

**Agreed details:**
- "No login in the 30 days before the as-of date" means no login from 1 to 30 September 2026 inclusive. An account's age is counted from its `created_date`.

**Not testable on this data:**
- Failed logins. The login data only records successful sign-ins, so every login counts.
- Locked accounts. An account's status is only active or disabled.

**Why:**
- Admin accounts should be used regularly by the people who need them. If one sits unused for a month, the access probably isn't needed, and it is exactly the kind of account an attacker or insider can use without the owner noticing. Thirty days is tighter than the usual threshold for standard accounts because of how much an admin account can do. It also sits well within the 90-day history, so every dormancy finding rests on data you actually have. Failed logins are left out because they show someone trying to get in, not legitimate use. Never-logged-in accounts get their own label because the history can't say how long they have really been unused, and the report shouldn't claim more than the data shows.
- Basing scope on open grants ties the test to what the account can actually do today, not to its name or past roles. Disabled accounts are left out because nobody can log in with them, so being unused isn't a risk. They are already handled by the leaver and access-removal processes.
- A new account with no logins yet is often just waiting for its owner to start, and flagging it would create false exceptions. Counting from the creation date gives every account the same fair window, and the account comes into scope automatically once that window has passed. Nothing has to be reviewed by hand.

---

## 5. Access not removed after a role change

**Purpose:** find people who moved department but kept access from their old job.
**Output:** one row per grant.
**Data:** `stg_hr_events` (mover events), `stg_employees` (current department and job title), `stg_access_grants`, `stg_accounts`, `stg_role_matrix`.

**Decide:**
- What makes a grant "old access": granted before the move date? Not in the role matrix for the person's current department and level? Both?
- How should a role that both the old and the new department are entitled to be treated?
- Is there a grace period after the move date?

**Rule:**
- A grant is old access only if both of these are true:
    1) It was granted before the person's most recent move date.
    2) It is not in the role matrix for the person's current department and level.
If a person has moved more than once, access from any earlier role counts, not just the last one.
- A role that is in the role matrix for both the old and the new department and level is not an exception. It carries over.
- Old access is an exception if it is still open more than 3 calendar days after the move date. A longer handover period is allowed only with documented approval from the new line manager, giving an end date. Privileged old access and old access that creates an SoD conflict with the new role get no grace period.

**Agreed details:**
- Two kinds of exception are reported. **Open:** the old access is still held on the as-of date, past the grace period. **Removed late:** the old access was removed after the grace period ended. The report shows the number of days late.
- Only current employees are tested. Leavers' access is check 1's job.
- The level comes from the job title (see "Level" above). The role matrix's IT "admin" level has no matching job title, so the administrator roles count as allowed for anyone currently in IT.
- A role in the matrix for both the old and the new department already passes condition 2, so it needs no extra logic.
- Grace periods are counted the same way with or without grace. The grace period ends N calendar days after the move date (N = 3, or 0 with no grace), and old access held on any day after that is an exception. With no grace, holding old access on the move date itself is allowed, but holding it the day after is not.
- "Creates an SoD conflict with the new role" means the old grant's function forms a pair in `stg_sod_rules` with a function of any role the person is entitled to now.

**Known limit:**
- The IT admin allowance means this check never flags an administrator role held by someone in IT, even if their job doesn't need it. This is acceptable because check 2 still tests whether every administrator grant was approved.

**Not testable on this data:**
- Approved handover extensions. The data has none, so every case gets the standard 3-day grace period.

**Why:**
- Each condition alone gives the wrong answer. "Granted before the move" alone would flag access the person is still entitled to and bury real findings in noise. "Not in the matrix" alone would also flag access granted after the move. That is a different failure, a bad new grant, and it belongs in a separate test with a different owner. Requiring both keeps the test focused on its purpose: access the person brought along that their new job doesn't justify. Counting earlier roles stops access from building up quietly across several moves, which is how long-serving staff end up with far more access than they need.
- Removing access and granting it again the same day reduces no risk. It only creates workload and disruption. The person is entitled to the role in their new job, so keeping it is correct. 
- People moving jobs often need their old access for a short time to hand over work, and flagging that from day one would penalise a normal, sensible practice. A fixed limit with approved extensions stops "handover" from becoming permanent. Privileged and SoD-conflicting access get no grace because the person now holds old and new powers together, and that combination can do harm immediately, handover or not.

---

## 6. Duplicate invoice

**Purpose:** find invoices entered (and possibly paid) more than once.
**Output:** one row per suspected duplicate: the later invoice of each matching pair.
**Data:** `stg_invoices` (vendor_id, vendor_invoice_number, invoice_date, amount), `stg_payments`.

**Decide:**
- Which fields must match: vendor, amount, invoice number? Exactly, or after tidying (case, spaces, dashes, leading zeros)?
- Must the invoices fall within some number of days of each other?
- Does it matter whether both were paid?

**Rule:**
- Before comparing, tidy each invoice number. First strip the leading zeros from each run of digits, then make it all capitals and remove spaces, dashes, slashes and dots. For example, "INV-0045-01" and "INV-45-1" both become "INV451". A run made up only of zeros becomes a single "0". Amounts must match exactly, using the gross amount in the same currency. Invoices are flagged in three tiers:
    1) Tier 1 (exact): same vendor, same tidied invoice number, same amount.
    2) Tier 2 (same number, different amount): same vendor, same tidied invoice number, different amount.
    3) Tier 3 (re-keyed): same vendor, same amount, different invoice number, with invoice dates within the window in the next rule
Leave out invoices that have been cancelled or reversed, or fully offset by a credit note.
- Tiers 1 and 2: no date window. The same invoice number from the same vendor is a duplicate however far apart the two entries are. Tier 3: the invoice dates must be within 7 days of each other.
- Payment status does not decide whether invoices are flagged. It only decides how serious the finding is:
    1) Critical: both invoices paid. Start recovery from the vendor.
    2) High: one paid and one open. Put a payment block on the open one at once.
    3) Medium: neither paid. Cancel the duplicate before the next payment run.
Each tier keeps its own ranking within these levels, so a Tier 1 duplicate with both paid comes first.

**Agreed details:**
- Where three or more invoices match, each later invoice appears once. It is paired with its earliest match, at the highest tier it reaches. Invoices are ordered by invoice date, then by invoice ID if the dates are equal. That ordering decides both which invoice is "later" and which match is "earliest".
- An invoice counts as paid if at least one payment is linked to it.

**Not testable on this data:**
- Excluding cancelled or reversed invoices and credit notes. Invoices have no status, and there are no credit notes.
- Matching on gross amount in the same currency. There is one amount per invoice and one currency, so the amount is used as it is.

**Why:**
- Duplicates rarely look identical. They usually come from someone typing "INV-0045" once and "inv45" the next time, so comparing the raw text misses the most common case. Tidying removes formatting differences without matching invoices that really are different. Exact amounts are kept because rounding would start matching unrelated invoices. The tiers reflect how confident each match is. Tier 1 is almost certainly a duplicate. Tier 2 may be an amended invoice entered as a new one. Tier 3 catches an invoice entered again under a mistyped number. This way the strongest matches get looked at first, and the weaker patterns still get checked.
- A vendor doesn't reuse an invoice number legitimately, so time doesn't make a repeat acceptable. A window there would only let late duplicates through, which are exactly the ones nobody remembers. Tier 3 needs a window because many legitimate invoices repeat the same amount: rent, subscriptions, monthly retainers. A short window catches someone entering the same bill twice without flagging every recurring monthly charge.
- A duplicate that hasn't been paid is still a control failure. The entry check didn't catch it, and if nobody acts it will be paid. Finding it before payment is the cheapest time to fix it. Payment status decides the response because it changes what's at stake. Once both are paid, the cash is gone and recovery depends on the vendor's cooperation. With one paid, there is a short window to stop the loss.

---

## 7. Split purchase

**Purpose:** find one purchase split into several POs to stay under the approval threshold.
**Output:** one row per PO, for every PO in a suspected split.
**Data:** `stg_purchase_orders` (vendor_id, po_date, amount, requested_by_hash, approved_by_hash).

**Decide:**
- Within how many days must the POs fall?
- Must they share the vendor? The requester? The approver?
- Must each be under the threshold and the total over it? Any minimum amount per PO?

**Rule:**
- POs are grouped if their creation dates fall within any 7-day rolling window, not fixed calendar weeks. Cancelled POs are left out.
- The POs must have the same vendor and the same requester. The approver does not have to match, but it affects severity
- For each approval limit L (the most a lower approver may approve), a group is flagged when every PO is ≤ L and the combined total is > L. POs above L are set aside before the group is tested, because they went to the higher approver anyway. Use the limit in force on each PO's date. Where the approval matrix has several levels, test the group against each level, and flag it against the highest level it crosses. There is no minimum amount per PO.
- For severity, High: the same approver approved every PO in the group, or every PO is within 10% below L, or all the POs were raised on the same day. Medium: all other groups that meet the above rules

**Agreed details:**
- Windows: a 7-day window starts at each PO, so the first and last PO in a group are at most 6 days apart. Each window only includes POs with the same vendor and requester. A PO is flagged if any window containing it qualifies.
- Setting large POs aside matters because, if one large PO made the whole window fail, someone could hide a split by raising a large, unrelated PO in the same week.

**Not testable on this data:**
- Excluding cancelled POs. POs have no status.
- Several approval levels. This data has one limit, L = 5,000,000, which doesn't change during the period.

**Why:**
- Someone splitting a purchase needs all the pieces raised close together, because the goods or services are needed at the same time. A short window catches that pattern without grouping unrelated purchases weeks apart. A rolling window is used because fixed weeks can be beaten by raising one PO on a Friday and the next on a Monday. Cancelled POs are excluded because they never committed any spend.
- The same vendor and requester within days is the clearest sign of one need being split up. Requiring the same approver would miss a common evasion: sending each piece to a different approver so nobody sees the whole purchase. When the approver is the same, it's a worse finding, because that person approved the pieces and should have noticed the pattern.
- This is the exact pattern of the abuse: each piece gets approved at a lower level, while the true purchase needed a more senior approver. If any one PO is already over the threshold, the higher approval was triggered anyway and there was nothing to avoid. Testing every level catches splits used to drop from, say, GMD approval to ED approval, not just the lowest limit. No minimum is set because splitting into many small POs is itself a way to avoid detection. Small routine purchases rarely add up to a threshold within a week, so leaving out a minimum adds little noise.
- These patterns separate deliberate splitting from coincidence. POs clustered just under the limit show that someone knew where the limit was. Raising them all the same day shows one need cut into pieces. A single approver signing all of them shows the review step failed too. Ranking these first sends investigation time to the cases most likely to be real.



---

## 8. Vendor bank account matches an employee's

**Purpose:** find vendors paid into an employee's own account.
**Output:** one row per vendor.
**Data:** `stg_vendors` (bank_account_hash), `stg_employees` (bank_account_hash, termination_date).

**Decide:**
- Compare against current employees only, or leavers too?

**Rule:**
- Compare vendor bank accounts against both current employees and leavers, with no cut-off date for leavers. A vendor is in scope if it is active, or if it was paid during the review period.
- Severity - Critical: the vendor was paid while the matched person was a current employee, or the matched person created or approved the vendor record. High: the person is a current employee and the vendor has not been paid yet, or the person is a leaver and the vendor was created or paid while they were employed. Medium: the person is a leaver and the vendor was created after they left, with no approved conflict-of-interest declaration on record.

**Agreed details:**
- "Current employee" is judged against the person's employment periods, including any period after a rehire. A payment made during a gap between leaving and being rehired counts as paid to a leaver.
- A case the tiers don't name: a current employee whose matched vendor was paid only before they were hired. It is rated High, the same as a current employee whose vendor hasn't been paid yet, because no payment was made while they were employed.

**Not testable on this data:**
- Vendor status. Vendors have no active or inactive flag, so every vendor in the master file is in scope.
- Conflict-of-interest declarations. There are none in the data, so every Medium case has no declaration on record.

**Why:**
- Leaving the bank doesn't make a payment to a staff member's account legitimate. It often makes it more suspicious. An employee can set up a vendor using their own account while employed and keep receiving payments after they leave, once nobody is watching. A leaver can also be used as a front by someone still inside. Testing current employees only would miss both cases. No cut-off is set because it is the vendor's activity that makes the match matter, not how long ago the person left.
- Money paid to a serving employee's own account through the vendor process is the clearest sign of fraud, and it is worse still if they set the vendor up themselves. A match with no payment yet is still serious, but there is time to stop it. A former employee hired as a consultant after leaving can be legitimate, so that case ranks lowest. It still needs a declared and approved relationship, because the bank's money is going to someone with inside knowledge.

---

## 9. Vendor created and paid on the same day

**Purpose:** find vendors set up and paid so fast that normal vetting can't have happened.
**Output:** one row per vendor.
**Data:** `stg_vendors` (created_date, approved_date), `stg_payments` (payment_date).

**Decide:**
- Same day only, or within some number of days?
- Measured from the creation date or the approval date?
- The vendor's first payment only, or any payment?

**Rule:**
- A vendor is flagged if its first payment is made within 3 business days of the vendor being created. Severity depends on how fast it was: 
    1) Critical: paid on the same day it was created, or paid before the vendor was approved.
    2) High: paid within 1 to 3 business days of creation.
- Measure from the vendor creation date, not the approval date. Report the approval date in the finding, so reviewers can see when it happened.
- Test the vendor's first payment. If it falls within the window, report all payments made inside the window and their total in the same finding. Payments after the window don't make a vendor fail this test.

**Not testable on this data:**
- Vendors created before 1 October 2024. Payment data starts on that date, so the first payment in the data may not be the vendor's real first payment. Only vendors created on or after 1 October 2024 are tested.

**Why:**
- Testing the same day only would be easy to beat: create the vendor today and pay it tomorrow. Proper vetting means checking documents, CAC registration, the TIN and the bank account, and that realistically takes more than a few days. A 3-business-day window catches rushed onboarding without flagging vendors that went through the normal process. Business days are used because weekends add calendar time without any vetting being done. A payment before approval gets the top severity because it shows the payment process doesn't check whether the vendor was approved, which is a control gap in itself as well as an exception.
- Vetting happens between creation and approval. If the clock started at approval, a vendor created, approved and paid within an hour would show a gap of zero after approval, but so would a vendor vetted properly for two weeks and then paid the day it was approved. The approval date can't tell those apart. The creation date measures the whole time available for vetting, which is what the test is about. If the approval date can also be rushed or backdated, it's the wrong anchor for a test meant to detect rushing.
- The first payment is the one that shows whether vetting was skipped. Later payments to a vendor that passed the window aren't evidence of rushed onboarding. Adding up every payment within the window shows how much money is exposed, which decides how urgently to act: a fraudulent vendor is often drained with several quick payments before anyone looks.

---

## 10. Payment with no matching invoice

**Purpose:** find money paid out without an invoice to support it.
**Output:** one row per payment.
**Data:** `stg_payments` (invoice_id, amount), `stg_invoices`.

**Decide:**
- Is "no matching invoice" only a missing invoice ID, or also a payment whose amount differs from its invoice?

**Rule:**
- A payment is unsupported if any of these is true: It has no invoice ID, Its invoice ID does not exist in the invoice data, The invoice is cancelled or reversed, The invoice belongs to a different vendor from the one paid. All of these are Critical.
- Amount differences are also tested, against all payments made on the invoice together. Flag an invoice as High when the total paid against it exceeds its gross amount, allowing only for rounding (e.g. ₦1). Paying less than the invoice is not an exception.

**Agreed details:**
- Overpayments are reported per payment. Payments on the invoice are ordered by payment date, then by payment ID. The payment that takes the running total over the invoice amount is flagged, with only the excess reported. Every later payment is flagged at its full amount.
- Two of the Critical conditions (an invoice ID that doesn't exist, and an invoice from a different vendor) are also dbt tests on the staging data. Those two tests are set to `warn`, so a failure doesn't stop the build, and this check is where the payments are reported. The scheduled run (Phase 5) must surface warnings, so they aren't lost in build logs.

**Not testable on this data:**
- Cancelled or reversed invoices. Invoices have no status.

**Why:**
- In each case, money left the bank with nothing behind it that shows a genuine debt to that payee. Checking only for a blank invoice ID would be weak, because a payment can quote a made-up, cancelled or borrowed invoice number and look supported. Matching the vendor matters most, since attaching another vendor's real invoice is an easy way to make a fraudulent payment look legitimate.
- An overpayment is unsupported in the same way as a payment with no invoice: the excess has no invoice behind it. The test adds up all payments together because one payment might look fine while three part-payments add up to more than the bill. Paying less is normal. Withholding tax is deducted before payment, and invoices are often paid in instalments. Flagging underpayments would bury the real overpayments in routine items.

---

## Change log

Any change to a rule after its first version, with the reason and the effect.

| Date | Check | Change | Reason | Score before | Score after |
|---|---|---|---|---|---|
| 2026-11-23 | Checks 1 and 5 | Added the "Account active" and "Entitled role" definitions: the disabled date is the first day gone, heads fall back to lead roles where a department has no head rows, and the IT admin allowance applies to both checks. | The data needed these meanings before check 1 could be built. Decided before any check was built or scored. | n/a (no results yet) | n/a |
| 2026-11-23 | All | Added shared definitions, agreed details and "Not testable on this data" notes after the implementability review. Rule changes: check 2 emergency approval due T+1, failures rated High; check 6 tidying order; check 7 written for each limit L (≤ L each, total > L) with POs above L set aside. | Rules must be implementable without guessing. Done before any check was built or scored. | n/a (no results yet) | n/a |
