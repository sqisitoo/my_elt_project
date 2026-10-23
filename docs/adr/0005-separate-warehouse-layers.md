# ADR-0005: Warehouse layout: RAW for loaded data, ANALYTICS by layer, one schema per developer

## Status

Proposed — 2026-10-23

## Context

Terraform creates two databases, `RAW` and `ANALYTICS`, and two schemas in `RAW`, one per
source. Nothing records what belongs where beyond the raw tables. `ANALYTICS` has no
schemas, no grants and no objects.

dbt fills that gap with defaults. `dbt_project.yml` sets no `database` or `schema`, so
every node goes to the target database and target schema. `profiles.yml` reads both from
`SNOWFLAKE_DATABASE` and `SNOWFLAKE_SCHEMA`. `ecs.tf` fills those from
`local.snowflake_creds`, which happens to reference `snowflake_schema.raw_air_pollution`.
The result is six models and the `cities_config` seed in `RAW.AIR_POLLUTION`, next to the
raw table and its stage. `stg_openweather__weather` reads `RAW.WEATHER` and writes into
`RAW.AIR_POLLUTION`.

The missing configuration is only the visible symptom, and any layout would fix it. What
is missing is a rule. Without one, the layout is whatever the defaults produce. Changing
the one line in `ecs.tf` would rebuild every node in `RAW.WEATHER`, and dbt never drops a
relation from its previous location, so the old ones would stay behind and keep answering
queries.

The layout decides four things:

- **What can be cleaned up safely.** dbt can rebuild everything it produced. It cannot
  rebuild raw data. Today both sit in one schema, so no schema-level operation separates
  them.
- **What a consumer can be given.** A BI consumer is planned. Access is granted per schema,
  and a grant on today's schema would also expose the raw JSON and the stage.
- **What privileges dbt needs.** dbt holds `CREATE VIEW` and `CREATE TABLE` on both RAW
  schemas. That is what let a model land in a neighbour's schema without an error.
- **Whether development and production collide.** The local `.env` carries the same
  database and schema as ECS, so a local `dbt build` replaces production relations. Local
  dbt runs under a different role, so the replaced objects change owner, and the next
  production run fails on `create or replace` (#24).

## Decision

The location of a relation follows two questions: who writes it, and whether it can be
rebuilt.

- `RAW` holds only what the load writes, one schema per source as today. No dbt object
  lives there.
- `ANALYTICS` holds everything dbt builds. In production it is split by layer: `STAGING`
  for staging models and seeds, `MARTS` for marts.
- Development builds go to one personal schema inside `ANALYTICS`, `DEV_VLAD`. Production
  schemas carry no prefix.

```
RAW
├── AIR_POLLUTION    raw table, stage
└── WEATHER          raw table, stage
ANALYTICS
├── STAGING          staging models, seeds    (production)
├── MARTS            marts                    (production)
└── DEV_VLAD         every dbt node           (local development)
```

## Alternatives considered

**Keep all dbt output in one RAW schema.** This is the current state. Rejected for the
reasons in Context.

**Keep staging in RAW next to the raw data; move only marts.** Staging stays close to the
data it cleans. Rejected because dbt rebuilds staging exactly like marts. RAW would keep
two writers, and dbt would keep `CREATE` privileges in RAW.

**Split ANALYTICS by source.** Mirrors RAW. Rejected because marts combine sources.
`dim_location` serves both facts and has no source to belong to, and every future shared
dimension (`dim_date`) repeats the problem. Staging does not need it either, because the
source is already part of every staging name (`stg_<source>__<entity>`).

**Let development share the production schemas.** The simplest layout. Rejected because a
local build replaces a production relation until the next scheduled run, up to a day. Two
roles owning objects in one schema also produce the failures from #24.

**Give development a prefixed copy of every layer, and production the same prefix.** This
is dbt's default behaviour: `DEV_VLAD_STAGING`, `DEV_VLAD_MARTS` locally and
`PROD_STAGING`, `PROD_MARTS` in production. Rejected because the production prefix tells a
consumer nothing, and one developer gains nothing from a per-layer copy.

## Consequences

RAW has a single writer. dbt no longer needs `CREATE` privileges there, and once they are
revoked, a misrouted node fails with a privilege error instead of landing silently. dbt
still shares table privileges on the raw tables with the load, because both run under one
role (#70).

Cleanup becomes a schema-level operation. Dropping a schema in `ANALYTICS` loses nothing a
`dbt build` cannot restore.

A BI consumer needs `SELECT` on `MARTS` and nothing else. Snowflake views run with their
owner's privileges, so the consumer needs no access to RAW.

No model SQL changes. `ref()` follows each node to its new location, and the sources
already name `RAW` explicitly. The relations left in `RAW.AIR_POLLUTION` are not removed
by dbt and are dropped by hand after the first green build in the new layout.

The layout is implemented by overriding `generate_schema_name` to delegate to dbt's
built-in `generate_schema_name_for_env`. In the `prod` target a custom schema is used
verbatim. In any other target every node goes to the target schema, which for local
development is `DEV_VLAD`.

dbt's target location now differs from the defaults of the loader's Airflow connection,
while both read the same variables today. dbt gets its own location variables. This is a
stopgap until the two jobs get separate identities (#70).

Isolation covers the computed layer only. Development reads production RAW, and the local
Airflow still loads into the production raw tables. A development RAW is not planned.

The local layout differs from production, because every node shares one schema. Names do
not collide, since the `stg_`, `dim_` and `fct_` prefixes are unique.
