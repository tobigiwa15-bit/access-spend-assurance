-- Staging: each account's first sign-in of the day, over the last 90 days.

with source as (

    select * from {{ source('raw', 'logins') }}

)

select
    login_id,
    account_id,
    cast(login_at as timestamp)       as login_at,
    date(cast(login_at as timestamp)) as login_date

from source
