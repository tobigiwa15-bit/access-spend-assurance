{#
    Tidies a vendor invoice number before duplicates are compared (check 6 in
    inventory/check_rules.md). Two steps, in this order:

    1. Strip the leading zeros from each run of digits.
       The pattern (^|\D)0+(\d) finds zeros that start a run of digits (at the
       start, or after a non-digit) and are followed by another digit. They are
       replaced by what came before and the digit after, so "0045" becomes "45".
       Because a digit must follow, a run of only zeros keeps one: "000" -> "0".
    2. Make it all capitals and remove spaces, dashes, slashes and dots.

    Example: "INV-0045-01" -> "INV-45-1" -> "INV451".
#}
{% macro tidy_invoice_number(column) -%}
regexp_replace(
    upper(regexp_replace({{ column }}, r'(^|\D)0+(\d)', r'\1\2')),
    r'[\s\-/.]',
    ''
)
{%- endmacro %}
