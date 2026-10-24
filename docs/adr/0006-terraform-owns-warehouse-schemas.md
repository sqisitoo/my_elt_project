# ADR-0006: Terraform owns the schemas in ANALYTICS

## Status

Accepted — 2026-10-24 (proposed 2026-10-23)

## Context

ADR-0005 places dbt output in three schemas inside `ANALYTICS`: `STAGING`, `MARTS` and
the development schema `DEV_VLAD`. Something has to create them. There are two
candidates:

- **Terraform**, which already creates both databases and the RAW schemas.
- **dbt itself.** Before a build, dbt runs `create schema if not exists` for every schema
  it needs, provided its role holds `CREATE SCHEMA` on the database.

Four facts about Snowflake and Terraform decide between them:

- `CREATE SCHEMA` is granted on a whole database. It cannot be limited to certain schema
  names.
- The role that creates an object owns it. The owner can drop the object and grant access
  to it to any role.
- dbt runs as `AIRFLOW_ROLE`. Its private key is injected into the environment of the ECS
  container, so every Airflow task and every installed dependency can act as that role.
- Terraform only sees objects in its state. An object created elsewhere does not appear in
  `terraform plan`, and Terraform cannot reference it reliably.

## Decision

Terraform creates every schema in `ANALYTICS`, the development schema included.

`AIRFLOW_ROLE` gets `USAGE` on `ANALYTICS`, and `USAGE`, `CREATE VIEW` and `CREATE TABLE`
on `STAGING` and `MARTS`. It gets no `CREATE SCHEMA`.

## Alternatives considered

**dbt creates the schemas.** A new schema takes one edit instead of two, development
schemas appear on their own, and consumer access could be granted through dbt's `+grants`
config. Rejected for four reasons:

- `AIRFLOW_ROLE` could create any schema in `ANALYTICS`.
- A typo in `+schema` would silently create a new schema. The build stays green, and
  consumers keep reading stale data from `MARTS`.
- `AIRFLOW_ROLE` would own the schemas. Any code holding its key could drop `MARTS` or
  open it to another role.
- The schemas would live outside Terraform state. On a fresh environment, any Terraform
  grant on them would need an apply, then a dbt run, then a second apply.

**Terraform creates the production schemas; dbt creates the development schema.** Local
dbt currently runs as `TERRAFORM_SVC`, which can already create schemas, so this costs
nothing today. Rejected because it breaks as soon as local dbt gets a narrower identity
(#70). At that point the development role needs `CREATE SCHEMA`, and if it is the same
role production uses, production loses the protection against typos. Keeping the
development schema in Terraform also keeps the list of schemas complete in one place.

## Consequences

A typo in `+schema` fails loudly. The schema does not exist, and dbt cannot create it.

The list of schemas lives in `snowflake.tf`, and every change to it goes through a pull
request.

Schema names are written in two places: `snowflake.tf` and the dbt side
(`dbt_project.yml`, plus the local environment for `DEV_VLAD`). A mismatch fails loudly
for the same reason as a typo. A single source of truth for these names is #40.

A new schema takes two edits, and their order matters. `terraform apply` goes first; in
the opposite order the first dbt build fails on a missing schema.

Grants for a future BI consumer, including future grants on views in `MARTS`, can live in
Terraform next to the schemas they apply to.

`AIRFLOW_ROLE` still owns every view and table it builds, so it can still drop them or
grant access to them. Control over the schemas stays with Terraform, and a grant on a view
is useless to a role that has no `USAGE` on its schema.
