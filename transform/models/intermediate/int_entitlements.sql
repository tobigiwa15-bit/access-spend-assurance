-- Intermediate: the roles each person is entitled to, from the role matrix.
-- One row per person per entitled role.
--
-- "Entitled role" in inventory/check_rules.md. A role is entitled if it is in
-- the matrix for the person's department and level, with two allowances:
--   1. Where a department has no "head" rows, a head gets its lead roles.
--   2. The IT "admin" roles count as entitled for anyone currently in IT.
-- Used by check 1 (does a rehire's access match their new role?) and check 5
-- (is access kept after a move still justified?).

with employees as (

    select * from {{ ref('int_employees') }}

),

matrix as (

    select * from {{ ref('stg_role_matrix') }}

),

departments_with_head_rows as (

    select distinct department
    from matrix
    where level = 'head'

)

select distinct
    employees.employee_hash,
    matrix.role

from employees
join matrix
    on matrix.department = employees.department

where
    -- the person's own level
    matrix.level = employees.level

    -- allowance 1: a head falls back to lead roles if the department has no head rows
    or (
        employees.level = 'head'
        and matrix.level = 'lead'
        and employees.department not in (select department from departments_with_head_rows)
    )

    -- allowance 2: admin roles for anyone in IT
    or (matrix.level = 'admin' and employees.department = 'IT')
