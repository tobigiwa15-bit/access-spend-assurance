"""
The fake company's access model: which roles exist, which combinations are
segregation-of-duties (SoD) conflicts, and which roles each department should have.

These are the reference tables a user access review starts from. In a real bank
they would come from each system's role catalogue, the SoD matrix owned by Risk,
and the role-based access (RBAC) matrix agreed with each department.

generate_data.py writes all three out as CSVs, and later steps use the matrix to
grant access when people join, move and leave.
"""

# --- Roles ------------------------------------------------------------------
# is_privileged: an administrator role. It can change system settings or other
#                users' access, so it can get around the system's own controls.
#                Approver roles are sensitive but not privileged: they work inside
#                the controls, and SOD_RULES is what keeps them in check.
# sod_function:  what the role lets you do, for SoD purposes. Two roles with
#                conflicting functions (see SOD_RULES) must not sit with one person,
#                even if they are in different systems.
ROLES = [
    # system,            role,                    privileged, sod_function,       description
    ("core_banking",     "cb_teller",               False, "cb_txn_initiate",  "Post cash deposits and withdrawals"),
    ("core_banking",     "cb_cs_officer",           False, "cb_cust_initiate", "Open accounts and change customer details, pending approval"),
    ("core_banking",     "cb_cs_supervisor",        False, "cb_cust_authorise", "Approve account openings and customer detail changes"),
    ("core_banking",     "cb_ops_officer",          False, "cb_txn_initiate",  "Process transfers, clearing and standing orders"),
    ("core_banking",     "cb_ops_supervisor",       False, "cb_txn_authorise", "Authorise transactions above officer limits"),
    ("core_banking",     "cb_gl_posting",           False, None,               "Post general ledger journals"),
    ("core_banking",     "cb_read_only",            False, None,               "View only"),
    ("core_banking",     "cb_sys_admin",            True,  "sys_admin",        "Change system parameters and limits"),
    ("core_banking",     "cb_user_admin",           True,  "user_admin",       "Create users and change their access"),
    ("payments_console", "pc_viewer",               False, None,               "View payments"),
    ("payments_console", "pc_initiator",            False, "payment_initiate", "Create payment batches"),
    ("payments_console", "pc_approver",             False, "payment_approve",  "Approve and release payment batches"),
    ("payments_console", "pc_admin",                True,  "sys_admin",        "Change beneficiaries, limits and users"),
    ("erp",              "erp_requisitioner",       False, None,               "Raise purchase requisitions"),
    ("erp",              "erp_ap_clerk",            False, "invoice_enter",    "Enter supplier invoices"),
    ("erp",              "erp_vendor_maintain",     False, "vendor_create",    "Create vendors and edit their bank details, pending approval"),
    ("erp",              "erp_vendor_approver",     False, "vendor_approve",   "Approve new vendors and bank detail changes"),
    ("erp",              "erp_payment_approver",    False, "payment_approve",  "Approve supplier payments"),
    ("erp",              "erp_read_only",           False, None,               "View only"),
    ("erp",              "erp_admin",               True,  "sys_admin",        "Change ERP settings and users"),
]

# --- SoD rules --------------------------------------------------------------
# Pairs of functions one person must not hold together, and the risk if they do.
SOD_RULES = [
    ("vendor_create",    "vendor_approve",   "Could set up a vendor or change its bank details and approve it without a second person"),
    ("vendor_create",    "payment_approve",  "Could set up a fake vendor and approve payments to it"),
    ("cb_cust_initiate", "cb_cust_authorise", "Could open an account or change customer details and approve it without a second person"),
    ("invoice_enter",    "payment_approve",  "Could enter a fake invoice and approve its payment"),
    ("payment_initiate", "payment_approve",  "Could create a payment and release it without a second person"),
    ("cb_txn_initiate",  "cb_txn_authorise", "Could post a transaction and authorise it without a second person"),
]

# --- Role matrix ------------------------------------------------------------
# The access each department *should* have. "staff" is everyone; "lead" covers
# team leads. The head of department gets the "head" roles if the department
# lists them, and the "lead" roles otherwise.
#
# Admins: IT leads, the Head of IT and one in every IT_STAFF_ADMIN_EVERY IT staff
# (the DBAs and application support people) get one admin role each, handed out
# in turn from IT_ADMIN_ROLES, so the admins are spread across systems.
READ_ONLY = ["cb_read_only", "pc_viewer", "erp_read_only"]

ROLE_MATRIX = {
    "Retail Banking":      {"staff": ["cb_teller", "cb_cs_officer"],
                            "lead":  ["cb_cs_supervisor", "cb_ops_supervisor"]},
    "Customer Service":    {"staff": ["cb_cs_officer"],
                            "lead":  ["cb_cs_supervisor"]},
    "Operations":          {"staff": ["cb_ops_officer"],
                            "lead":  ["cb_ops_supervisor"]},
    "Payments Operations": {"staff": ["pc_initiator", "cb_read_only"],
                            "lead":  ["pc_approver", "cb_read_only"]},
    "Treasury":            {"staff": ["pc_initiator"],
                            "lead":  ["pc_approver"]},
    "Finance":             {"staff": ["erp_ap_clerk", "cb_gl_posting"],
                            "lead":  ["erp_payment_approver", "cb_gl_posting"]},
    "Procurement":         {"staff": ["erp_requisitioner", "erp_vendor_maintain"],
                            "lead":  ["erp_requisitioner", "erp_vendor_approver"],
                            # The head approves POs above the threshold, so must not
                            # be able to raise them.
                            "head":  ["erp_vendor_approver"]},
    "Human Resources":     {"staff": ["erp_requisitioner"],
                            "lead":  ["erp_requisitioner"]},
    "Risk and Compliance": {"staff": READ_ONLY, "lead": READ_ONLY},
    "Internal Audit":      {"staff": READ_ONLY, "lead": READ_ONLY},
    "IT":                  {"staff": ["cb_read_only"],
                            "lead":  ["cb_read_only"]},
}
IT_ADMIN_ROLES = ["cb_sys_admin", "cb_user_admin", "pc_admin", "erp_admin"]
IT_STAFF_ADMIN_EVERY = 4


def check_model_is_clean():
    """Stop if the model itself breaks its own rules.

    The clean data must contain no SoD conflicts, so that every conflict the checks
    find later is one we planted on purpose. This is a control on the generator.
    """
    role_names = {r[1] for r in ROLES}
    function_of = {r[1]: r[3] for r in ROLES}
    conflicts = {frozenset((a, b)) for a, b, _ in SOD_RULES}

    sets_to_check = [(dept, level, roles)
                     for dept, levels in ROLE_MATRIX.items()
                     for level, roles in levels.items()]
    # An IT admin holds their usual IT roles plus one admin role.
    sets_to_check += [("IT", f"{level} + {admin}", ROLE_MATRIX["IT"][level] + [admin])
                      for level in ROLE_MATRIX["IT"]
                      for admin in IT_ADMIN_ROLES]

    for dept, level, roles in sets_to_check:
        unknown = set(roles) - role_names
        assert not unknown, f"{dept} {level}: unknown roles {unknown}"
        functions = {function_of[r] for r in roles} - {None}
        for pair in conflicts:
            assert not pair <= functions, f"{dept} {level}: SoD conflict {set(pair)}"
