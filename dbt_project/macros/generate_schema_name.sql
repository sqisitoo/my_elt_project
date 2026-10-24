{#
    Schema routing for the warehouse layout (ADR-0005).

    Overrides dbt's default `generate_schema_name`, which would prefix every custom
    schema with the target schema (`DEV_VLAD_STAGING`, `PROD_MARTS`). It does two
    things.

    Guard: a model, seed or snapshot without `+schema` is a compiler error in every
    target except `dev`. dbt calls this macro at parse time for every node, and CI
    runs `dbt parse --target ci`, so a new folder without `+schema` fails the pull
    request instead of landing in the target schema in production. `dev` is exempt
    because every node goes to `DEV_VLAD` there on purpose. The check is on
    `node.resource_type` because tests also pass through this macro and are not part
    of the layout.

    Routing: the logic of dbt's built-in `generate_schema_name_for_env`, written out
    here so the routing rule is owned by this project and cannot change with a dbt
    upgrade:

    - target `prod`: a node's `+schema` is used verbatim (`STAGING`, `MARTS`).
    - any other target: every node goes to the target schema (`DEV_VLAD` locally),
      and `+schema` is ignored.

    The checks are on the target NAME, so a production run must use `--target prod`.

    TRAP: dbt cannot create schemas here (ADR-0006). A `+schema` that has no
    matching schema in `terraform/snowflake.tf` fails the prod build, but only the
    prod build: the guard checks that `+schema` is set, not that it is spelled right.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if target.name != 'dev'
        and custom_schema_name is none
        and node.resource_type in ['model', 'seed', 'snapshot'] -%}
        {{ exceptions.raise_compiler_error(
            node.resource_type ~ " '" ~ node.unique_id ~ "' has no +schema. Every model,"
            ~ " seed and snapshot must set one in dbt_project.yml (ADR-0005)."
        ) }}
    {%- endif -%}

    {%- if target.name == 'prod' and custom_schema_name is not none -%}
        {{ custom_schema_name | trim }}
    {%- else -%}
        {{ target.schema }}
    {%- endif -%}
{%- endmacro %}
