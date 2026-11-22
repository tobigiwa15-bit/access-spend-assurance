{#
  Keyed hash for personal identifiers (employee IDs, bank account numbers).

  A plain SHA-256 of 'E00001' can be reversed by hashing all 2,000 possible IDs
  and comparing. Mixing in a secret key (HASH_SALT, kept in .env and GitHub
  secrets, never in the repo) stops that: without the key the hashes can't be
  matched back to anyone.

  Every model uses this one macro, so the same person gets the same hash in
  every table, and the agent can follow them from accounts to approvals to vendors.

  The hash is cut to 16 hex characters (64 bits). That's ample to keep ~2,500
  values distinct (the unique tests would catch a clash) and short enough for
  people, and the agent, to copy without mistakes. NULL stays NULL.

  Textbook keyed hashing uses HMAC. BigQuery has no HMAC function, and a secret
  prefix gives the same protection against the risk here, which is guessing.
#}
{% macro hash_pii(column) -%}
    substr(to_hex(sha256(concat('{{ env_var("HASH_SALT") }}', '|', cast({{ column }} as string)))), 1, 16)
{%- endmacro %}
