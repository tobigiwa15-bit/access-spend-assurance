{#
    Business days from start_date to end_date: Monday to Friday, no public
    holidays ("Business day" in inventory/check_rules.md). Counting starts the
    day after start_date, so Friday to the following Monday is 1.

    How: list every date in the range, keep the weekdays, count them.
    BigQuery's dayofweek runs 1 = Sunday to 7 = Saturday.

    Returns 0 if end_date is on or before start_date, or if either is empty,
    so a caller with an open-ended date must fill it in first (e.g. with the
    as-of date).
#}
{% macro business_days_between(start_date, end_date) -%}
(
    select count(*)
    from unnest(generate_date_array(date_add({{ start_date }}, interval 1 day), {{ end_date }})) as day
    where extract(dayofweek from day) not in (1, 7)
)
{%- endmacro %}
