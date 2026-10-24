{#
    Schema routing for the warehouse layout (ADR-0005).

    Overrides dbt's default `generate_schema_name`, which would prefix every custom
    schema with the target schema (`DEV_VLAD_STAGING`, `PROD_MARTS`). The logic is
    the one of dbt's built-in `generate_schema_name_for_env`, written out here so the
    routing rule is owned by this project and cannot change with a dbt upgrade:

    - target `prod`: a node's `+schema` is used verbatim (`STAGING`, `MARTS`); a node
      without one goes to the target schema.
    - any other target: every node goes to the target schema (`DEV_VLAD` locally),
      and `+schema` is ignored.

    The check is on the target NAME, so a production run must use `--target prod`.

    TRAP: dbt cannot create schemas here (ADR-0006). A `+schema` that has no
    matching schema in `terraform/snowflake.tf` fails the prod build, but only the
    prod build: in dev the value is ignored, so a typo stays invisible locally.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if target.name == 'prod' and custom_schema_name is not none -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ target.schema }}
    {%- endif -%}
{%- endmacro %}
