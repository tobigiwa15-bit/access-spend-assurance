{#
  Masks a bank account number for display: 0123456789 becomes ******6789.
  Enough for a person to recognise an account, not enough to use it.
  Checks that compare accounts use hash_pii() on the full number instead.
#}
{% macro mask_account(column) -%}
    concat('******', right({{ column }}, 4))
{%- endmacro %}
