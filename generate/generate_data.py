"""
Phase 1: generate the synthetic company data.

So far this builds:
  employees     the HR roster as it stands on the AS_OF date, one row per person
  hr_events     the history behind it: joiner, mover, leaver and rehire events
  roles         every role in the three systems (from access_model.py)
  sod_rules     pairs of functions one person must not hold together
  role_matrix   the roles each department should have
  accounts      one account per person per system they have ever had access to
  access_grants every role ever granted, with its approval and removal dates
  logins        each account's first sign-in of the day, over the last 90 days
  vendors       the vendor master file
  purchase_orders, invoices, payments
                the purchase-to-pay flow over the two-year audit period

Everything comes from one fixed seed and one fixed "as of" date, so anyone who
runs this gets identical files.

Run from the project folder, with .venv active:
    python generate/generate_data.py
"""

import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

import access_model

# --- Settings ---------------------------------------------------------------
SEED = 42                      # change this and every table changes
AS_OF = date(2026, 9, 30)      # the fake company's "today". Never use date.today():
                               # the data would change every time it ran.
COMPANY_START = date(2015, 1, 1)

N_EMPLOYEES = 2000
LEAVER_RATE = 0.12             # share of the roster who have left
MOVER_RATE = 0.10              # share who changed department at some point
CONTRACTOR_RATE = 0.08         # share hired as contractors rather than permanent staff
LEAD_RATE = 0.12               # share of each department who are team leads

# Look-alike: a leaver who came back as a contractor. Their HR record still shows
# them as a leaver (contractors are tracked by event, not by a new roster row), so
# the "leaver with an active account" check will flag them. The only thing that
# clears them is the rehire event in hr_events.
N_REHIRED_AS_CONTRACTOR = 12

# Access settings
SYSTEMS_LIVE = date(2015, 3, 1)    # access records start when the three systems went live
APPROVAL_MAX_LEAD_DAYS = 3         # access is approved 0-3 days before it is granted
LEAVER_REVOKE_MAX_LAG_DAYS = 2     # leavers lose access 0-2 days after their last day
                                   # (the HR feed to IT isn't instant). The leaver check
                                   # will need a grace period to allow for this.

# Login settings
LOGIN_DAYS = 90                    # login history covers the 90 days up to AS_OF
LOW_USE_ROLES = {"cb_read_only", "pc_viewer", "erp_read_only", "erp_requisitioner"}
LOGIN_RATE_LOW = 0.30              # chance of logging in on a working day, view-only users
LOGIN_RATE_NORMAL = 0.85           # everyone else uses their systems most days
MUST_LOG_IN_WITHIN_DAYS = 30       # every account still active on AS_OF has logged in
                                   # within this many days, so the clean data has no
                                   # dormant accounts. Only planted ones will be dormant.

# Spend settings (amounts in naira)
N_VENDORS = 500
VENDORS_FROM = date(2016, 1, 1)    # earliest vendor in the master file
SPEND_START = date(2024, 10, 1)    # the audit period: 1 Oct 2024 to AS_OF
APPROVAL_THRESHOLD = 5_000_000     # POs above this need the Head of Procurement;
                                   # up to it, a Procurement team lead can approve
MONTHLY_VENDOR_RATE = 0.10         # share of vendors who bill every month
VENDOR_FIRST_USE_DAYS = 14         # a new vendor isn't used until 14+ days after approval
MIN_PO_GAP_DAYS = 16               # an ad hoc vendor's POs are spaced at least 16 days
                                   # apart, and at least 14 after weekend dates move to
                                   # Monday, so the clean data has no split purchases

AD_HOC_CATEGORIES = ["IT services", "Consulting", "Stationery and printing", "Training",
                     "Marketing", "Office equipment", "Legal services"]
MONTHLY_CATEGORIES = ["Facilities management", "Security services", "Cleaning",
                      "Telecoms", "Utilities"]
VENDOR_BANKS = ["Harbour Bank", "Savannah Trust Bank", "Lagoon Commercial Bank",
                "Plateau Bank", "Delta Union Bank", "Northgate Bank"]   # all invented

OUT_DIR = Path(__file__).resolve().parent.parent / "data"

# Each department and its share of headcount (adds up to 1.0)
DEPARTMENTS = {
    "Retail Banking": 0.20,
    "Operations": 0.15,
    "Customer Service": 0.12,
    "IT": 0.12,
    "Payments Operations": 0.10,
    "Finance": 0.08,
    "Risk and Compliance": 0.07,
    "Procurement": 0.04,
    "Treasury": 0.04,
    "Human Resources": 0.04,
    "Internal Audit": 0.04,
}
STAFF_TITLES = ["Associate", "Officer", "Senior Officer", "Analyst", "Senior Analyst"]


def random_date(rng, start, end):
    """A random date from start to end, both included."""
    return start + timedelta(days=rng.randint(0, (end - start).days))


# --- employees --------------------------------------------------------------
def make_employees(rng, fake):
    rows = []
    used_emails = set()

    for i in range(1, N_EMPLOYEES + 1):
        first, last = fake.first_name(), fake.last_name()

        # Two people can share a name, so add a number until the email is unique.
        email = f"{first}.{last}@company.example".lower()
        n = 2
        while email in used_emails:
            email = f"{first}.{last}{n}@company.example".lower()
            n += 1
        used_emails.add(email)

        hire_date = random_date(rng, COMPANY_START, AS_OF)

        # Only someone with at least 30 days' service can be a leaver.
        termination_date = None
        if rng.random() < LEAVER_RATE and (AS_OF - hire_date).days > 30:
            termination_date = random_date(rng, hire_date + timedelta(days=30), AS_OF)

        rows.append({
            "employee_id": f"E{i:05d}",
            "full_name": f"{first} {last}",
            "email": email,
            "department": rng.choices(list(DEPARTMENTS), weights=list(DEPARTMENTS.values()))[0],
            "job_title": None,      # filled in below, once we know who manages whom
            "manager_id": None,
            "employment_type": "contractor" if rng.random() < CONTRACTOR_RATE else "permanent",
            "hire_date": hire_date,
            "termination_date": termination_date,
            # Salary account number (10 digits). Needed later for the
            # "vendor bank account matches an employee's" check.
            "bank_account_number": f"{rng.randrange(10**10):010d}",
        })

    # Reporting lines, one department at a time:
    #   head of department = the longest-serving person still employed, reports to no one
    #   team leads         = a random LEAD_RATE of the rest, report to the head
    #   everyone else      = reports to a random team lead
    for dept in DEPARTMENTS:
        people = [r for r in rows if r["department"] == dept]
        current = sorted((r for r in people if r["termination_date"] is None),
                         key=lambda r: r["hire_date"])
        head = current[0]
        others = [r for r in people if r is not head]
        leads = rng.sample(others, max(1, round(len(others) * LEAD_RATE)))

        head["job_title"] = f"Head of {dept}"
        for r in leads:
            r["job_title"] = "Team Lead"
            r["manager_id"] = head["employee_id"]
        for r in others:
            if r not in leads:
                r["job_title"] = rng.choice(STAFF_TITLES)
                r["manager_id"] = rng.choice(leads)["employee_id"]

    return pd.DataFrame(rows)


# --- hr_events --------------------------------------------------------------
def make_hr_events(employees, rng):
    events = []
    people = employees.to_dict("records")

    # Movers: people with enough service to have changed department part-way through.
    # The roster shows where they are now, so the move is *from* another department.
    def last_day(p):
        return p["termination_date"] or AS_OF

    can_move = [p for p in people if (last_day(p) - p["hire_date"]).days > 60]
    movers = rng.sample(can_move, round(N_EMPLOYEES * MOVER_RATE))
    moved_from = {}
    for p in movers:
        old_dept = rng.choice([d for d in DEPARTMENTS if d != p["department"]])
        moved_from[p["employee_id"]] = old_dept
        events.append({
            "employee_id": p["employee_id"],
            "event_type": "mover",
            "event_date": random_date(rng, p["hire_date"] + timedelta(days=30),
                                      last_day(p) - timedelta(days=1)),
            "from_department": old_dept,
            "to_department": p["department"],
            "employment_type": None,
        })

    # Joiners and leavers: every hire and every termination is an event.
    for p in people:
        events.append({
            "employee_id": p["employee_id"],
            "event_type": "joiner",
            "event_date": p["hire_date"],
            "from_department": None,
            # A mover joined their *original* department.
            "to_department": moved_from.get(p["employee_id"], p["department"]),
            "employment_type": p["employment_type"],
        })
        if p["termination_date"] is not None:
            events.append({
                "employee_id": p["employee_id"],
                "event_type": "leaver",
                "event_date": p["termination_date"],
                "from_department": p["department"],
                "to_department": None,
                "employment_type": None,
            })

    # Rehires (look-alike): permanent staff who left at least 60 days before AS_OF
    # and came back as contractors to the same department, 2 weeks to 6 months later.
    can_rehire = [p for p in people
                  if p["termination_date"] is not None
                  and p["employment_type"] == "permanent"
                  and (AS_OF - p["termination_date"]).days >= 60]
    for p in rng.sample(can_rehire, N_REHIRED_AS_CONTRACTOR):
        latest = min(180, (AS_OF - p["termination_date"]).days)
        events.append({
            "employee_id": p["employee_id"],
            "event_type": "rehire",
            "event_date": p["termination_date"] + timedelta(days=rng.randint(14, latest)),
            "from_department": None,
            "to_department": p["department"],
            "employment_type": "contractor",
        })

    # Put events in date order and number them.
    events.sort(key=lambda e: (e["event_date"], e["employee_id"], e["event_type"]))
    for i, e in enumerate(events, start=1):
        e["event_id"] = f"EV{i:05d}"

    columns = ["event_id", "employee_id", "event_type", "event_date",
               "from_department", "to_department", "employment_type"]
    return pd.DataFrame(events)[columns]


# --- Reference tables -------------------------------------------------------
def make_reference_tables():
    """Turn the access model into tables. No randomness here."""
    roles = pd.DataFrame(access_model.ROLES,
                         columns=["system", "role", "is_privileged", "sod_function", "description"])
    sod_rules = pd.DataFrame(access_model.SOD_RULES,
                             columns=["function_a", "function_b", "risk"])
    role_matrix = pd.DataFrame(
        [(dept, level, role)
         for dept, levels in access_model.ROLE_MATRIX.items()
         for level, role_list in levels.items()
         for role in role_list],
        columns=["department", "level", "role"],
    )
    return roles, sod_rules, role_matrix


# --- accounts and access_grants ---------------------------------------------
# Clean joiner-mover-leaver (JML) process: we replay each person's HR history and
# apply the role matrix at every step.
#   joiner  -> grant the department's roles, approved by a manager
#   mover   -> remove roles the new department doesn't need (on the move date),
#              grant the new ones, keep any role both departments have
#   leaver  -> remove everything, 0-2 days after the last day
#   rehire  -> grant the department's staff roles again (the account is reused)
# No issues are planted here. That happens in a separate pass, so the answer key
# lists exactly what was planted.

def is_employed(person, day):
    """True if the person was on the payroll on that day (last day included)."""
    left = person["termination_date"]
    return person["hire_date"] <= day and (left is None or day <= left)


def level_of(person):
    title = person["job_title"]
    if title.startswith("Head of"):
        return "head"
    return "lead" if title == "Team Lead" else "staff"


def make_access(employees, hr_events, rng):
    people = employees.to_dict("records")
    system_of = {r[1]: r[0] for r in access_model.ROLES}

    # Managers by department, used to pick approvers.
    head_of = {p["department"]: p for p in people if p["job_title"].startswith("Head of")}
    leads_in = {d: [p for p in people if p["department"] == d and p["job_title"] == "Team Lead"]
                for d in DEPARTMENTS}

    # IT leads and the Head of IT get one admin role each, handed out in turn.
    it_leads = [p for p in people if p["department"] == "IT" and level_of(p) in ("lead", "head")]
    admin_role = {p["employee_id"]: access_model.IT_ADMIN_ROLES[i % len(access_model.IT_ADMIN_ROLES)]
                  for i, p in enumerate(it_leads)}

    # The mover and rehire events, looked up by employee.
    moves = {e["employee_id"]: (e["event_date"], e["from_department"])
             for e in hr_events.to_dict("records") if e["event_type"] == "mover"}
    rehires = {e["employee_id"]: e["event_date"]
               for e in hr_events.to_dict("records") if e["event_type"] == "rehire"}

    def roles_for(person, dept, level):
        levels = access_model.ROLE_MATRIX[dept]
        if level == "head" and "head" not in levels:
            level = "lead"   # most departments give their head the lead roles
        roles = list(levels[level])
        if dept == "IT" and level == "lead":
            roles.append(admin_role[person["employee_id"]])
        return roles

    def pick_approver(person, dept, level, day):
        """A manager in the department, employed on that day, who isn't the requester.
        Staff are approved by a team lead, leads by the head of department, and heads
        by another head of department."""
        def ok(c):
            return c["employee_id"] != person["employee_id"] and is_employed(c, day)

        candidates = [c for c in leads_in[dept] if ok(c)] if level == "staff" else []
        if not candidates and ok(head_of[dept]):
            candidates = [head_of[dept]]
        if not candidates:
            candidates = [h for h in head_of.values() if ok(h)]
        if not candidates:  # only possible in the company's first weeks
            candidates = [c for c in people if ok(c)]
        return rng.choice(candidates)["employee_id"]

    grants = []
    for p in people:
        eid = p["employee_id"]

        # The person's HR history as steps: (date, department, level).
        # A department of None means they left.
        if eid in moves:
            move_date, old_dept = moves[eid]
            steps = [(p["hire_date"], old_dept, "staff"), (move_date, p["department"], level_of(p))]
        else:
            steps = [(p["hire_date"], p["department"], level_of(p))]
        if p["termination_date"] is not None:
            steps.append((p["termination_date"], None, None))
        if eid in rehires:
            steps.append((rehires[eid], p["department"], "staff"))

        # Anything before go-live collapses into one step on the go-live date.
        before = [s for s in steps if s[0] < SYSTEMS_LIVE]
        steps = [s for s in steps if s[0] >= SYSTEMS_LIVE]
        if before and before[-1][1] is not None:
            steps.insert(0, (SYSTEMS_LIVE, before[-1][1], before[-1][2]))

        open_grants = {}  # role -> the grant that is currently active
        for day, dept, level in steps:
            if dept is None:  # leaver: remove everything
                revoke_on = min(day + timedelta(days=rng.randint(0, LEAVER_REVOKE_MAX_LAG_DAYS)), AS_OF)
                for g in open_grants.values():
                    g["revoked_date"] = revoke_on
                open_grants = {}
                continue

            new_roles = roles_for(p, dept, level)
            for role in [r for r in open_grants if r not in new_roles]:
                open_grants.pop(role)["revoked_date"] = day

            to_grant = [r for r in new_roles if r not in open_grants]
            if to_grant:
                # One access request per HR step, covering all the new roles.
                approval_date = day - timedelta(days=rng.randint(0, APPROVAL_MAX_LEAD_DAYS))
                approver = pick_approver(p, dept, level, approval_date)
                for role in to_grant:
                    g = {"employee_id": eid, "system": system_of[role], "role": role,
                         "grant_type": "standard", "approver_id": approver,
                         "approval_date": approval_date, "granted_date": day,
                         "revoked_date": None}
                    grants.append(g)
                    open_grants[role] = g

    # Accounts: one per person per system. An account is active while any of its
    # grants is still open; otherwise it was disabled when its last grant was removed.
    username = {p["employee_id"]: p["email"].split("@")[0] for p in people}
    by_account = {}
    for g in grants:
        by_account.setdefault((g["employee_id"], g["system"]), []).append(g)

    accounts = []
    for (eid, system), gs in by_account.items():
        still_open = any(g["revoked_date"] is None for g in gs)
        accounts.append({
            "employee_id": eid,
            "system": system,
            "username": username[eid],
            "status": "active" if still_open else "disabled",
            "created_date": min(g["granted_date"] for g in gs),
            "disabled_date": None if still_open else max(g["revoked_date"] for g in gs),
        })

    # Number the accounts in the order they were created, then link each grant to its account.
    accounts.sort(key=lambda a: (a["created_date"], a["employee_id"], a["system"]))
    account_id = {}
    for i, a in enumerate(accounts, start=1):
        a["account_id"] = f"A{i:05d}"
        account_id[(a["employee_id"], a["system"])] = a["account_id"]

    for g in grants:
        g["account_id"] = account_id[(g["employee_id"], g["system"])]
    grants.sort(key=lambda g: (g["granted_date"], g["account_id"], g["role"]))
    for i, g in enumerate(grants, start=1):
        g["grant_id"] = f"G{i:05d}"

    accounts = pd.DataFrame(accounts)[["account_id", "employee_id", "system", "username",
                                       "status", "created_date", "disabled_date"]]
    grants = pd.DataFrame(grants)[["grant_id", "account_id", "role", "grant_type", "approver_id",
                                   "approval_date", "granted_date", "revoked_date"]]
    return accounts, grants


# --- logins -----------------------------------------------------------------
# One row per account per day it was used: the first sign-in of that day.
# An account can only be used on a working day when its owner is at work and
# it has at least one open grant. So there are no logins after someone leaves,
# none on a system after a mover's access to it was removed, and none between
# a rehired contractor's leaving date and their return.

def make_at_work(employees, hr_events):
    """Return a function that says whether someone was working on a given day:
    employed, or back as a rehired contractor."""
    people = {p["employee_id"]: p for p in employees.to_dict("records")}
    rehired_on = {e["employee_id"]: e["event_date"]
                  for e in hr_events.to_dict("records") if e["event_type"] == "rehire"}

    def at_work(eid, day):
        back = eid in rehired_on and day >= rehired_on[eid]
        return is_employed(people[eid], day) or back

    return at_work


def make_logins(employees, hr_events, accounts, access_grants, rng):
    at_work = make_at_work(employees, hr_events)
    grants_of = {}
    for g in access_grants.to_dict("records"):
        grants_of.setdefault(g["account_id"], []).append(g)

    def open_roles(account_id, day):
        # A grant is open from its granted_date up to the day before its revoked_date.
        return {g["role"] for g in grants_of[account_id]
                if g["granted_date"] <= day and (g["revoked_date"] is None or day < g["revoked_date"])}

    first_day = AS_OF - timedelta(days=LOGIN_DAYS - 1)
    all_days = [first_day + timedelta(days=i) for i in range(LOGIN_DAYS)]
    working_days = [d for d in all_days if d.weekday() < 5]   # Monday to Friday
    recent_cutoff = AS_OF - timedelta(days=MUST_LOG_IN_WITHIN_DAYS)

    logins = []
    for a in accounts.to_dict("records"):
        login_days = []
        usable_days = []
        for d in working_days:
            roles = open_roles(a["account_id"], d)
            if not roles or not at_work(a["employee_id"], d):
                continue
            usable_days.append(d)
            rate = LOGIN_RATE_LOW if roles <= LOW_USE_ROLES else LOGIN_RATE_NORMAL
            if rng.random() < rate:
                login_days.append(d)

        # A light user can go weeks without logging in by chance. Make sure every
        # account still active on AS_OF has at least one recent login.
        recent = [d for d in usable_days if d > recent_cutoff]
        if a["status"] == "active" and recent and not any(d > recent_cutoff for d in login_days):
            login_days.append(rng.choice(recent))

        for d in sorted(login_days):
            minute = rng.randint(7 * 60 + 30, 10 * 60)   # between 07:30 and 10:00
            logins.append({"account_id": a["account_id"],
                           "login_at": datetime.combine(d, time(minute // 60, minute % 60))})

    logins.sort(key=lambda x: (x["login_at"], x["account_id"]))
    for i, x in enumerate(logins, start=1):
        x["login_id"] = f"L{i:06d}"
    return pd.DataFrame(logins)[["login_id", "account_id", "login_at"]]


# --- Spend: vendors, purchase_orders, invoices, payments --------------------
# Every person in the spend data held the right role on the day they acted:
#   vendor created by        erp_vendor_maintain    (Procurement staff)
#   vendor approved by       erp_vendor_approver    (Procurement leads)
#   PO raised by             erp_requisitioner
#   PO approved by           delegation of authority: a Procurement team lead up
#                            to APPROVAL_THRESHOLD, the Head of Procurement above it
#                            (or the Head of Finance, if the Head of Procurement
#                            raised the PO)
#   invoice entered by       erp_ap_clerk           (Finance staff)
#   payment approved by      erp_payment_approver   (Finance leads)
# This is what makes the planted SoD cases meaningful: the access data and the
# spend data describe the same people.

def on_weekday(day):
    """Move a Saturday or Sunday forward to Monday."""
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def make_spend(employees, hr_events, accounts, access_grants, rng, fake):
    at_work = make_at_work(employees, hr_events)
    people = employees.to_dict("records")

    # Who held each role, and when.
    owner = dict(zip(accounts["account_id"], accounts["employee_id"]))
    held = {}
    for g in access_grants.to_dict("records"):
        held.setdefault(g["role"], []).append((owner[g["account_id"]], g["granted_date"], g["revoked_date"]))

    def pick_holder(role, day, not_this=None):
        """Someone at work who held the role on that day."""
        candidates = sorted({eid for eid, start, end in held[role]
                             if start <= day and (end is None or day < end)
                             and at_work(eid, day) and eid != not_this})
        if not candidates:
            raise RuntimeError(f"Nobody held {role} on {day}. Adjust the settings.")
        return rng.choice(candidates)

    head_of_procurement = next(p for p in people if p["job_title"] == "Head of Procurement")
    head_of_finance = next(p for p in people if p["job_title"] == "Head of Finance")
    procurement_leads = [p for p in people
                         if p["department"] == "Procurement" and p["job_title"] == "Team Lead"]

    def po_approver(amount, day, requester):
        """Delegation of authority for purchase orders."""
        if amount <= APPROVAL_THRESHOLD:
            leads = [p["employee_id"] for p in procurement_leads
                     if is_employed(p, day) and p["employee_id"] != requester]
            if leads:
                return rng.choice(leads)
        # The Head of Procurement can't raise POs any more, but could have raised
        # some in an earlier job before moving in. Nobody approves their own PO.
        if requester == head_of_procurement["employee_id"]:
            return head_of_finance["employee_id"]
        return head_of_procurement["employee_id"]

    employee_accounts = set(employees["bank_account_number"])

    vendors, pos, invoices, payments = [], [], [], []
    used_names, used_bank_accounts = set(), set()

    for v in range(1, N_VENDORS + 1):
        vendor_id = f"V{v:04d}"

        name = fake.company()
        while name in used_names:
            name = fake.company()
        used_names.add(name)

        # A bank account number that no other vendor and no employee has.
        bank_account = f"{rng.randrange(10**10):010d}"
        while bank_account in used_bank_accounts or bank_account in employee_accounts:
            bank_account = f"{rng.randrange(10**10):010d}"
        used_bank_accounts.add(bank_account)

        monthly = rng.random() < MONTHLY_VENDOR_RATE
        created = on_weekday(random_date(rng, VENDORS_FROM, AS_OF - timedelta(days=60)))
        created_by = pick_holder("erp_vendor_maintain", created)
        approved = on_weekday(created + timedelta(days=rng.randint(0, 5)))
        approved_by = pick_holder("erp_vendor_approver", approved, not_this=created_by)

        vendors.append({
            "vendor_id": vendor_id,
            "vendor_name": name,
            "category": rng.choice(MONTHLY_CATEGORIES if monthly else AD_HOC_CATEGORIES),
            "billing": "monthly" if monthly else "ad hoc",
            "bank_name": rng.choice(VENDOR_BANKS),
            "bank_account_number": bank_account,
            "created_date": created,
            "created_by": created_by,
            "approved_date": approved,
            "approved_by": approved_by,
        })

        # Spending starts at the audit period, or once the new vendor is ready.
        spend_from = max(SPEND_START, approved + timedelta(days=VENDOR_FIRST_USE_DAYS))
        prefix = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3))

        # Each vendor's invoices: (po_index, invoice_date, amount).
        # po_index points into this vendor's own list of POs, built alongside.
        vendor_pos, vendor_invoices = [], []

        if monthly:
            # Usage-based monthly bills: the amount varies month to month.
            # One blanket PO covers each 12 invoices.
            base = rng.lognormvariate(13.3, 0.6)          # median about 600,000 a month
            billing_day = rng.randint(1, 5)
            year, month = spend_from.year, spend_from.month
            dates = []
            while date(year, month, billing_day) <= AS_OF:
                d = date(year, month, billing_day)
                if d >= spend_from:
                    dates.append(on_weekday(d))
                year, month = (year + 1, 1) if month == 12 else (year, month + 1)
            for i, d in enumerate(dates):
                if i % 12 == 0:
                    vendor_pos.append((d - timedelta(days=7), round(base * 12 * 1.1, -3)))
                vendor_invoices.append((len(vendor_pos) - 1, d, round(base * rng.uniform(0.85, 1.15), 2)))
        else:
            # Ad hoc: a PO every so often, each invoiced once in full.
            mean_gap = rng.randint(30, 180)
            d = spend_from + timedelta(days=rng.randint(0, mean_gap))
            while d <= AS_OF:
                po_date = on_weekday(d)
                # Mostly modest amounts with a long tail: median 1.5m, about 1 in 9 above 5m.
                amount = round(min(max(rng.lognormvariate(14.22, 1.0), 25_000), 40_000_000), 2)
                vendor_pos.append((po_date, amount))
                invoice_date = on_weekday(po_date + timedelta(days=rng.randint(5, 40)))
                if invoice_date <= AS_OF:
                    vendor_invoices.append((len(vendor_pos) - 1, invoice_date, amount))
                d += timedelta(days=max(MIN_PO_GAP_DAYS, round(mean_gap * rng.uniform(0.5, 1.5))))

        po_ids = []
        for po_date, amount in vendor_pos:
            requester = pick_holder("erp_requisitioner", po_date)
            po = {"vendor_id": vendor_id, "po_date": po_date, "amount": amount,
                  "requested_by": requester, "approved_by": po_approver(amount, po_date, requester)}
            pos.append(po)
            po_ids.append(po)

        for n, (po_index, invoice_date, amount) in enumerate(vendor_invoices, start=1):
            inv = {"vendor_id": vendor_id, "po": po_ids[po_index],
                   "vendor_invoice_number": f"{prefix}-{n:04d}",
                   "invoice_date": invoice_date, "amount": amount,
                   "entered_by": pick_holder("erp_ap_clerk", invoice_date)}
            invoices.append(inv)
            # Paid on 14-45 day terms; anything due after AS_OF is still unpaid.
            pay_date = on_weekday(invoice_date + timedelta(days=rng.randint(14, 45)))
            if pay_date <= AS_OF:
                payments.append({"vendor_id": vendor_id, "invoice": inv,
                                 "payment_date": pay_date, "amount": amount,
                                 "approved_by": pick_holder("erp_payment_approver", pay_date)})

    # Number everything in date order, then swap object links for IDs.
    pos.sort(key=lambda x: (x["po_date"], x["vendor_id"]))
    for i, x in enumerate(pos, start=1):
        x["po_id"] = f"PO{i:05d}"
    invoices.sort(key=lambda x: (x["invoice_date"], x["vendor_id"], x["vendor_invoice_number"]))
    for i, x in enumerate(invoices, start=1):
        x["invoice_id"] = f"INV{i:05d}"
        x["po_id"] = x.pop("po")["po_id"]
    payments.sort(key=lambda x: (x["payment_date"], x["vendor_id"], x["invoice"]["invoice_id"]))
    for i, x in enumerate(payments, start=1):
        x["payment_id"] = f"PAY{i:05d}"
        x["invoice_id"] = x.pop("invoice")["invoice_id"]

    vendors = pd.DataFrame(vendors)
    pos = pd.DataFrame(pos)[["po_id", "vendor_id", "po_date", "amount", "requested_by", "approved_by"]]
    invoices = pd.DataFrame(invoices)[["invoice_id", "vendor_id", "po_id", "vendor_invoice_number",
                                       "invoice_date", "amount", "entered_by"]]
    payments = pd.DataFrame(payments)[["payment_id", "vendor_id", "invoice_id", "payment_date",
                                       "amount", "approved_by"]]
    return vendors, pos, invoices, payments


# --- Run --------------------------------------------------------------------
def main():
    # One random generator for our own choices, and Faker seeded the same way for names.
    # Tables are generated in a fixed order. Later tables will be added *after* these,
    # so adding them won't change the tables that already exist.
    rng = random.Random(SEED)
    fake = Faker("en_NG")
    fake.seed_instance(SEED)

    access_model.check_model_is_clean()   # stops here if the model breaks its own SoD rules

    employees = make_employees(rng, fake)
    hr_events = make_hr_events(employees, rng)
    roles, sod_rules, role_matrix = make_reference_tables()
    accounts, access_grants = make_access(employees, hr_events, rng)
    logins = make_logins(employees, hr_events, accounts, access_grants, rng)
    vendors, purchase_orders, invoices, payments = make_spend(
        employees, hr_events, accounts, access_grants, rng, fake)

    OUT_DIR.mkdir(exist_ok=True)
    tables = {
        "employees": employees,
        "hr_events": hr_events,
        "roles": roles,
        "sod_rules": sod_rules,
        "role_matrix": role_matrix,
        "accounts": accounts,
        "access_grants": access_grants,
        "logins": logins,
        "vendors": vendors,
        "purchase_orders": purchase_orders,
        "invoices": invoices,
        "payments": payments,
    }
    for name, df in tables.items():
        # lineterminator="\n" keeps the files byte-identical on Windows and on
        # GitHub's Linux machines (Windows would otherwise end lines with \r\n).
        df.to_csv(OUT_DIR / f"{name}.csv", index=False, lineterminator="\n")
        print(f"{name:<12} {len(df):>6,} rows")

    print("\nhr_events by type:")
    print(hr_events["event_type"].value_counts().to_string())


if __name__ == "__main__":
    main()
