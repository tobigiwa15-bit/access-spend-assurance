"""
Plant known issues and look-alikes into the clean data, and record each one in
the answer key.

In audit terms this is a test deck: known items fed through the controls to see
which ones they catch. The clean data has been checked to contain none of these
issues, so after this runs, every issue in the data is one listed in the answer key.

  seeded_issue  a real control failure the check should flag
  look_alike    a legitimate case the check will probably flag too, which only
                more evidence (another table) can clear

Each person is used for at most one case, so cases don't overlap.
Planting has its own random generator, so changing what we plant never changes
the clean data underneath.

generate_data.py calls plant_access() after building the clean tables. The tables
arrive as lists of dicts (one dict per row) and are changed in place.
"""

from datetime import datetime, time, timedelta

# --- How many of each -------------------------------------------------------
N_LEAVER_ACTIVE = 10        # leaver whose account was never disabled
N_PRIV_NO_APPROVAL = 8      # admin role granted with no approval record
N_EMERGENCY_RETRO = 8       # look-alike: emergency admin access, approved the next day or two
N_DORMANT_PRIV = 6          # admin account with no logins in the last 90 days
N_MOVER_KEPT_ACCESS = 10    # mover who kept a role from their old department

# SoD conflicts: (department, role the person already has, conflicting role added).
# Two people for each pattern. The second Procurement pattern crosses systems:
# vendor set-up in the ERP, payment release in the payments console.
SOD_PATTERNS = [
    ("Procurement",         "erp_vendor_maintain", "erp_payment_approver"),
    ("Procurement",         "erp_vendor_maintain", "pc_approver"),
    ("Finance",             "erp_ap_clerk",        "erp_payment_approver"),
    ("Payments Operations", "pc_initiator",        "pc_approver"),
    ("Customer Service",    "cb_cs_officer",       "cb_cs_supervisor"),
]
SOD_PER_PATTERN = 2

LOGIN_WINDOW_DAYS = 90      # must match LOGIN_DAYS in generate_data.py


# --- Small helpers ----------------------------------------------------------
_counter = {"n": 0}


def new_id(prefix):
    """A temporary ID. generate_data.assign_ids() replaces every ID afterwards."""
    _counter["n"] += 1
    return f"new-{prefix}{_counter['n']}"


def weekdays_between(start, end):
    return [start + timedelta(days=i) for i in range((end - start).days + 1)
            if (start + timedelta(days=i)).weekday() < 5]


def is_staff(person):
    return person["job_title"] != "Team Lead" and not person["job_title"].startswith("Head of")


def add_case(key, check, case_type, entity_type, entity, id_field, description):
    """Record one case. `entity` is the row itself (a dict) so its ID can be read
    after the IDs are renumbered; id_field says which field holds the ID."""
    key.append({"check_name": check, "case_type": case_type, "entity_type": entity_type,
                "entity": entity, "id_field": id_field, "description": description})


# --- Access issues ----------------------------------------------------------
def plant_access(t, rng, as_of, at_work):
    """Plant the access issues and look-alikes. Returns the answer-key cases."""
    key = []
    used = set()   # employees already in a case

    emp = {p["employee_id"]: p for p in t["employees"]}
    role_info = {r["role"]: r for r in t["roles"]}
    conflicts = [frozenset((s["function_a"], s["function_b"])) for s in t["sod_rules"]]
    window_start = as_of - timedelta(days=LOGIN_WINDOW_DAYS - 1)

    accounts_of = {}
    for a in t["accounts"]:
        accounts_of.setdefault(a["employee_id"], []).append(a)
    grants_of = {}
    for g in t["access_grants"]:
        grants_of.setdefault(g["account_id"], []).append(g)

    events = t["hr_events"]
    rehired = {e["employee_id"] for e in events if e["event_type"] == "rehire"}
    moved_on = {e["employee_id"]: e["event_date"] for e in events if e["event_type"] == "mover"}
    moved_from = {e["employee_id"]: e["from_department"] for e in events if e["event_type"] == "mover"}

    def open_grants(eid):
        return [g for a in accounts_of.get(eid, []) for g in grants_of.get(a["account_id"], [])
                if g["revoked_date"] is None]

    def has_sod_conflict(roles):
        functions = {role_info[r]["sod_function"] for r in roles} - {None}
        return any(pair <= functions for pair in conflicts)

    def in_post_since(p):
        """When the person started their current job: hire date, or move date for movers."""
        return moved_on.get(p["employee_id"], p["hire_date"])

    def is_admin(eid):
        return any(role_info[g["role"]]["is_privileged"] for g in open_grants(eid))

    def current_staff(dept):
        return [p for p in t["employees"]
                if p["department"] == dept and is_staff(p) and p["termination_date"] is None
                and p["employee_id"] not in used and p["employee_id"] not in rehired]

    def add_logins(account_id, start, end, rate, at_least_one=False):
        """Logins for an account that had none in this period (so no day is doubled)."""
        days = weekdays_between(max(start, window_start), min(end, as_of))
        chosen = [d for d in days if rng.random() < rate]
        if at_least_one and not chosen:
            chosen = [rng.choice(days)]
        for day in chosen:
            minute = rng.randint(7 * 60 + 30, 10 * 60)
            t["logins"].append({"login_id": new_id("L"), "account_id": account_id,
                                "login_at": datetime.combine(day, time(minute // 60, minute % 60))})

    def add_grant(account, role, grant_type, approver, approval_date, granted, revoked):
        g = {"grant_id": new_id("G"), "account_id": account["account_id"], "role": role,
             "grant_type": grant_type, "approver_id": approver, "approval_date": approval_date,
             "granted_date": granted, "revoked_date": revoked}
        t["access_grants"].append(g)
        grants_of.setdefault(account["account_id"], []).append(g)
        return g

    # 1. Look-alike: leavers rehired as contractors (already in the clean data).
    #    The leaver check sees a leaver with an active account; the rehire event
    #    and the new grant dated on the rehire day clear them.
    for eid in sorted(rehired):
        used.add(eid)
        for a in accounts_of[eid]:
            if a["status"] == "active":
                add_case(key, "leaver_active_account", "look_alike", "account", a, "account_id",
                         f"Left on {emp[eid]['termination_date']}, rehired as a contractor; "
                         f"{a['system']} access re-granted on return")

    # 2. Leavers whose account was never disabled. Half of them also kept using it.
    candidates = []
    for p in t["employees"]:
        left = p["termination_date"]
        if left is None or p["employee_id"] in used:
            continue
        if not (as_of - timedelta(days=540) <= left <= as_of - timedelta(days=30)):
            continue
        for a in accounts_of.get(p["employee_id"], []):
            last_grants = [g for g in grants_of[a["account_id"]]
                           if g["revoked_date"] is not None and g["revoked_date"] >= left]
            if last_grants and not any(role_info[g["role"]]["is_privileged"] for g in last_grants):
                candidates.append((p, a, last_grants))
                break
    for i, (p, a, last_grants) in enumerate(rng.sample(candidates, N_LEAVER_ACTIVE)):
        used.add(p["employee_id"])
        for g in last_grants:
            g["revoked_date"] = None
        a["status"], a["disabled_date"] = "active", None
        detail = "never disabled"
        if i % 2 == 0:
            add_logins(a["account_id"], p["termination_date"] + timedelta(days=1), as_of, 0.15,
                       at_least_one=True)
            detail = "never disabled, and used after leaving"
        add_case(key, "leaver_active_account", "seeded_issue", "account", a, "account_id",
                 f"Left on {p['termination_date']}; {a['system']} account {detail}")

    # IT staff with a core banking account and no admin role, in post for at least
    # 4 months: the pool for unapproved admin grants and emergency (look-alike) grants.
    it_pool = []
    for p in current_staff("IT"):
        cb = [a for a in accounts_of.get(p["employee_id"], [])
              if a["system"] == "core_banking" and a["status"] == "active"]
        if cb and not is_admin(p["employee_id"]) and in_post_since(p) <= as_of - timedelta(days=120):
            it_pool.append((p, cb[0]))
    picks = rng.sample(it_pool, N_PRIV_NO_APPROVAL + N_EMERGENCY_RETRO)
    head_of_it = next(p for p in t["employees"] if p["job_title"] == "Head of IT")

    # 3. Admin role granted with no approval on record. Three were later removed,
    #    the rest are still active.
    for i, (p, cb) in enumerate(picks[:N_PRIV_NO_APPROVAL]):
        used.add(p["employee_id"])
        start = max(as_of - timedelta(days=365), in_post_since(p))
        granted = rng.choice(weekdays_between(start, as_of - timedelta(days=70)))
        revoked = granted + timedelta(days=rng.randint(20, 60)) if i < 3 else None
        role = ["cb_sys_admin", "cb_user_admin"][i % 2]
        g = add_grant(cb, role, "standard", None, None, granted, revoked)
        add_case(key, "privileged_without_approval", "seeded_issue", "grant", g, "grant_id",
                 f"{role} granted on {granted} with no approval"
                 + (f", removed {revoked}" if revoked else ", still active"))

    # 4. Look-alike: emergency admin access for an incident, approved by the Head of
    #    IT a day or two after it was granted, and removed within three days.
    for i, (p, cb) in enumerate(picks[N_PRIV_NO_APPROVAL:]):
        used.add(p["employee_id"])
        start = max(as_of - timedelta(days=365), in_post_since(p))
        granted = rng.choice(weekdays_between(start, as_of - timedelta(days=10)))
        role = ["cb_sys_admin", "cb_user_admin"][i % 2]
        g = add_grant(cb, role, "emergency", head_of_it["employee_id"],
                      granted + timedelta(days=rng.randint(1, 2)), granted,
                      granted + timedelta(days=rng.randint(1, 3)))
        add_case(key, "privileged_without_approval", "look_alike", "grant", g, "grant_id",
                 f"Emergency {role} on {granted}, approved retrospectively by the Head of IT "
                 f"on {g['approval_date']}, removed {g['revoked_date']}")

    # 5. SoD conflicts: a conflicting role added and approved by the line manager,
    #    who didn't spot the conflict.
    for dept, has_role, add_role in SOD_PATTERNS:
        system = role_info[add_role]["system"]
        pool = []
        for p in current_staff(dept):
            eid = p["employee_id"]
            manager = emp.get(p["manager_id"])
            if manager is None or manager["termination_date"] is not None:
                continue
            if max(in_post_since(p), manager["hire_date"]) > as_of - timedelta(days=90):
                continue   # too new in post for a later role change
            if has_role not in {g["role"] for g in open_grants(eid)}:
                continue
            in_system = [a for a in accounts_of.get(eid, []) if a["system"] == system]
            if in_system and in_system[0]["status"] != "active":
                continue   # skip people with a disabled account in that system
            pool.append((p, manager, in_system[0] if in_system else None))
        for p, manager, account in rng.sample(pool, SOD_PER_PATTERN):
            eid = p["employee_id"]
            used.add(eid)
            start = max(as_of - timedelta(days=540), in_post_since(p),
                        manager["hire_date"] + timedelta(days=3))
            granted = rng.choice(weekdays_between(start, as_of - timedelta(days=30)))
            if account is None:   # first access to this system: a new account
                account = {"account_id": new_id("A"), "employee_id": eid, "system": system,
                           "username": accounts_of[eid][0]["username"], "status": "active",
                           "created_date": granted, "disabled_date": None}
                t["accounts"].append(account)
                accounts_of[eid].append(account)
                add_logins(account["account_id"], granted, as_of, 0.5)
            add_grant(account, add_role, "standard", manager["employee_id"],
                      granted - timedelta(days=rng.randint(0, 3)), granted, None)
            add_case(key, "sod_conflict", "seeded_issue", "employee", eid, None,
                     f"Holds {has_role} and was granted {add_role} on {granted}")

    # 6. Dormant admin accounts: IT staff whose admin role sits on its own account
    #    (payments console or ERP) and who haven't used it in 90 days. They still
    #    log in to core banking every day, so they are at work.
    dormant_pool = []
    for p in current_staff("IT"):
        for a in accounts_of.get(p["employee_id"], []):
            roles = [g["role"] for g in grants_of[a["account_id"]] if g["revoked_date"] is None]
            if (a["status"] == "active" and a["system"] != "core_banking"
                    and roles and all(role_info[r]["is_privileged"] for r in roles)
                    and a["created_date"] <= as_of - timedelta(days=120)):
                dormant_pool.append((p, a, roles[0]))
    for p, a, role in rng.sample(dormant_pool, N_DORMANT_PRIV):
        used.add(p["employee_id"])
        t["logins"][:] = [x for x in t["logins"] if x["account_id"] != a["account_id"]]
        add_case(key, "dormant_privileged_account", "seeded_issue", "account", a, "account_id",
                 f"{role} on {a['system']}, no login in the last {LOGIN_WINDOW_DAYS} days")

    # 7. Movers who kept one role from their old department. The role mustn't be
    #    one they need now, mustn't be privileged, and mustn't create an SoD conflict
    #    (that would be a different case).
    mover_pool = []
    for p in t["employees"]:
        eid = p["employee_id"]
        if eid not in moved_on or eid in used or p["termination_date"] is not None:
            continue
        moved = moved_on[eid]
        if not (as_of - timedelta(days=3 * 365) <= moved <= as_of - timedelta(days=30)):
            continue
        current_roles = {g["role"] for g in open_grants(eid)}
        for a in accounts_of[eid]:
            for g in grants_of[a["account_id"]]:
                if (g["revoked_date"] == moved and g["role"] not in current_roles
                        and not role_info[g["role"]]["is_privileged"]
                        and not has_sod_conflict(current_roles | {g["role"]})):
                    mover_pool.append((p, a, g))
    seen = set()
    unique_pool = []
    for p, a, g in mover_pool:   # one candidate grant per person
        if p["employee_id"] not in seen:
            seen.add(p["employee_id"])
            unique_pool.append((p, a, g))
    for i, (p, a, g) in enumerate(rng.sample(unique_pool, N_MOVER_KEPT_ACCESS)):
        used.add(p["employee_id"])
        g["revoked_date"] = None
        if a["status"] == "disabled":   # the account had been closed with the move
            a["status"], a["disabled_date"] = "active", None
            if i % 2 == 0:
                add_logins(a["account_id"], moved_on[p["employee_id"]], as_of, 0.3)
        add_case(key, "access_not_removed_after_move", "seeded_issue", "grant", g, "grant_id",
                 f"Moved from {moved_from[p['employee_id']]} to {p['department']} on "
                 f"{moved_on[p['employee_id']]}; kept {g['role']}")

    return key


def answer_key_rows(key):
    """Turn the cases into answer-key rows, reading each entity's final ID."""
    rows = []
    for c in key:
        entity_id = c["entity"][c["id_field"]] if c["id_field"] else c["entity"]
        rows.append({"check_name": c["check_name"], "case_type": c["case_type"],
                     "entity_type": c["entity_type"], "entity_id": entity_id,
                     "description": c["description"]})
    rows.sort(key=lambda r: (r["check_name"], r["case_type"], r["entity_id"]))
    for i, r in enumerate(rows, start=1):
        r["case_id"] = f"K{i:03d}"
    return rows
