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

Everything comes from one fixed seed and one fixed "as of" date, so anyone who
runs this gets identical files.

Run from the project folder, with .venv active:
    python generate/generate_data.py
"""

import random
from datetime import date, timedelta
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
    return "lead" if title == "Team Lead" or title.startswith("Head of") else "staff"


def make_access(employees, hr_events, rng):
    people = employees.to_dict("records")
    system_of = {r[1]: r[0] for r in access_model.ROLES}

    # Managers by department, used to pick approvers.
    head_of = {p["department"]: p for p in people if p["job_title"].startswith("Head of")}
    leads_in = {d: [p for p in people if p["department"] == d and p["job_title"] == "Team Lead"]
                for d in DEPARTMENTS}

    # IT leads get one admin role each, handed out in turn.
    it_leads = [p for p in people if p["department"] == "IT" and level_of(p) == "lead"]
    admin_role = {p["employee_id"]: access_model.IT_ADMIN_ROLES[i % len(access_model.IT_ADMIN_ROLES)]
                  for i, p in enumerate(it_leads)}

    # The mover and rehire events, looked up by employee.
    moves = {e["employee_id"]: (e["event_date"], e["from_department"])
             for e in hr_events.to_dict("records") if e["event_type"] == "mover"}
    rehires = {e["employee_id"]: e["event_date"]
               for e in hr_events.to_dict("records") if e["event_type"] == "rehire"}

    def roles_for(person, dept, level):
        roles = list(access_model.ROLE_MATRIX[dept][level])
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

    OUT_DIR.mkdir(exist_ok=True)
    tables = {
        "employees": employees,
        "hr_events": hr_events,
        "roles": roles,
        "sod_rules": sod_rules,
        "role_matrix": role_matrix,
        "accounts": accounts,
        "access_grants": access_grants,
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
