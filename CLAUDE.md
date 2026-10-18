# my_elt_project — Project Context

> Committed, English. Personal notes and anything not for a public reader live in
> `CLAUDE.local.md` (gitignored) — read both when working locally.

## Purpose

Learning/portfolio data engineering project (owner: Vlad, github.com/sqisitoo/my_elt_project).
Goal: practice production-grade DE patterns; the repo doubles as a job-search showcase.
Prefer production best practices over shortcuts. Explain reasoning when suggesting
patterns — this is a learning project, and understanding the "why" is the deliverable.

## What it does

ELT pipelines ingesting OpenWeatherMap data (air pollution + historical weather) for 5 EU
cities (seed `dbt_project/seeds/cities_config.csv`) into S3 (bronze, partitioned JSON) →
Snowflake RAW via `COPY INTO` from external stages → dbt staging/marts models.

## Stack

- **Orchestration:** Airflow 3.1.6 (TaskFlow API via `airflow.sdk`, dynamic task mapping
  `.expand()`), Python 3.10.
- **Transform:** dbt-snowflake in a separate venv inside the Airflow image
  (`$DBT_VENV_PATH`), invoked via BashOperator
  (`plugins/common/utils/dbt.py::build_dbt_command`). Unpinned in the Dockerfile
  (currently 1.11.x), so new-syntax deprecations are live — see Conventions.
- **Warehouse:** Snowflake, key-pair auth for service users. RAW db, schemas
  AIR_POLLUTION and WEATHER. ALL dbt models currently build into `RAW.AIR_POLLUTION`
  (`SNOWFLAKE_DATABASE=RAW`, no `+database`/`+schema` in `dbt_project.yml`); the
  ANALYTICS db exists in Terraform but is unused — #44 (separate warehouse layers).
- **Infra:** Terraform (`terraform/`) — AWS VPC, ECS Fargate (monolith task: apiserver +
  scheduler + dag-processor), RDS Postgres 17 (Airflow metadata), S3 datalake, ECR,
  Secrets Manager, GitHub OIDC. Snowflake provider (~2.14) manages
  databases/schemas/tables/stages/storage integration/RBAC.
- **CI/CD:** `.github/workflows/ci_cd.yml`. Every PR to main runs lint, Terraform and dbt
  validation, and pytest; build/push to ECR (OIDC) and ECS deploy run only on push to
  main or `workflow_dispatch`. What CI does not catch — see Gotchas.
- **Config:** pydantic-settings (`plugins/common/config/settings.py`, `SecretStr`); source
  registry `sources.yml` (name → target_schema / table / s3_stage / `s3_prefix`).
  `s3_prefix` is the bronze root and is read by BOTH sides: extract writes under it, load
  copies from under it. Cities come from the dbt seed CSV.

## Layout

- `dags/` — thin DAG definitions (`weather_snowflake_dag`, `air_pollution_snowflake_dag`)
  plus `dbt_debug.py` (debug DAG `__test_dbt_integration`, `schedule=None`). The debug DAG
  IS in the dag-bag, so DAG-contract tests must account for it.
- `plugins/common/clients/` — `OpenWeatherApiClient`, `S3Service`, `SnowflakeClient`
  (`COPY INTO` by partition prefix, no `FILES`; `FORCE = FALSE` +
  `LOAD_UNCERTAIN_FILES = TRUE`, ADR-0004).
- `plugins/common/utils/bronze_paths.py` — **the single home of the bronze key layout**
  (ADR-0003, ADR-0004). `object_key` MUST be composed on top of `partition_prefix`: that
  is what keeps the writer and `COPY INTO` on one date format (pinned by
  `test_object_key_nests_under_its_partition_prefix`). Never assemble a bronze path by
  hand.
- `plugins/pipelines/<pipeline>/extract.py` — pure business logic with DI of clients;
  raises `AirflowSkipException` on empty API data; never hardcodes the bronze root.
- `tests/` — pytest (clients, extract functions, DAG contract tests).
  `dbt_project/tests/` is a DIFFERENT directory: dbt singular tests in SQL.
- `dbt_project/models/`:
  - staging has two input families: `staging/open_weather/stg_openweather__*` (API
    payloads: LATERAL FLATTEN, `try_cast`, coordinate rounding, surrogate keys, dedup via
    `qualify row_number`) and `staging/internal/stg_internal__locations.sql` (from the
    seed). Any mart joining locations goes through `stg_internal__locations`, never
    through the seed.
  - `src_openweather.yml` declares TWO sources (`openweather_air_pollution`,
    `openweather_weather`), because dbt allows `database`/`schema` only per source.
  - `marts/core`: `dim_location`, `fct_air_quality`, `fct_weather`. No materialization
    config, so they are views. Contracts are not enforced yet.
  - `dbt_project/tests/`: one singular test,
    `assert_fct_weather_has_24_hours_per_location_day.sql`.
- `dbt_project/macros/` — `round_coordinate` (the single home of coordinate rounding);
  shared doc blocks for coordinate columns live in `models/_shared_contract_docs.md`.
- `docs/adr/` — architecture decision records. `docs/ROADMAP.md` — status and phases.
- `research/` — scratch notebooks, excluded from lint and from git.

## Conventions

### Repository

- English for everything that lands in the repository; Russian in conversation only.
- Conventional commits (feat/fix/chore/refactor + scope); a feature branch per change.
  PRs land as squash merge, so intra-branch commit messages are working notes — don't
  spend effort rewording them.
- ruff (line 110, E/W/F/B/I/UP) + mypy (pydantic plugin) + pytest. Run `make check`
  (`lint` + `lint_dbt` + `test`) before finishing. `lint_tf` is NOT part of `check`:
  Terraform is not in the dev container and runs on the host, where `apply` runs.
- Every multi-line Makefile target starts with `set -eo pipefail` (reason: comment at the
  top of the Makefile).
- The Terraform version lives in two places on purpose: `required_version` in
  `terraform/main.tf` and the exact version in the `setup-terraform` step. Change both; a
  mismatch fails `terraform init`.
- Dependencies are installed with Airflow constraint files (`make install_deps`).
- Heavy imports go inside `@task` functions (fast DAG parsing).
- Secrets: `.env` (template `.env.template`), AWS Secrets Manager in prod; `keys/` is
  gitignored.

### dbt

- Property files use the new syntax: `data_tests:` (not `tests:`), test parameters under
  `arguments:`, test config (`severity`, `where`) under a sibling `config:`.
- Naming: `stg_<source>__<entity>`, sources in `src_<source>.yml`, per-model yml with
  docs and tests.
- **Model docs:** the model `description` states the grain ("Grain: one row per …").
  Every measure documents its unit, its permitted aggregation (SUM / AVG only / none for
  circular `wind_direction_degree`) and its traps. A description that restates the column
  name counts as missing.
- **Where to put a test:** ask "can THIS model break this property", not "do I trust the
  layer above". Measure tests are not duplicated into marts; keys ARE tested at the mart
  boundary (unique/not_null on surrogates, not_null/relationships on FKs, plus a grain
  test) — the join can break them, and they are the mart's public contract.
- That rule covers data, not concurrency. Do NOT remove `unique` on `location_id` in
  `stg_internal__locations` as redundant: it is the test that caught the two-DAG race (see
  Known open defects).
- **Measure completeness** (ADR-0002): structural columns and measures the source always
  provides → `not_null`, default severity. Measures where absence is legal (`rain_1h_mm`,
  `snow_1h_mm`, `wind_gust_*`) → no `not_null`; the description says what NULL means.
  Any non-default severity carries a comment with its reason and removal condition.
- Coordinates are rounded to 4 decimals everywhere — it is the join key to
  `dim_location`. Round only through `round_coordinate`, document coordinate columns via
  shared doc blocks. Never `round(..., 4)` by hand.

### Process

- **ADR:** `docs/adr/NNNN-slug.md` (Status / Context / Decision / Alternatives /
  Consequences, about a page) when two of three hold: hard to reverse, real alternatives
  existed, would defend it at review. Written before implementation as `Proposed`;
  accepted ADRs are never edited, only superseded. Details in ADR-0001.
  **Claude proposes an ADR on its own** when a decision meets the criterion — one line,
  naming which two "yes" fired, before implementation. Never write one unasked; if
  declined, do not raise it again for that decision.
- **Do not breed issues.** Open one only if the owner can restate the problem and will
  come back to it. A one- or two-line fix gets fixed now; something noticed but not yet
  understood goes into Gotchas. Reference issues as number + substance. Exception: the
  `learning-debt` label — deferred improvements for after the finish line, each with a
  "why I want this" line, opened only by the owner.

## Status and roadmap

Status, phases and the finish line live in [`docs/ROADMAP.md`](docs/ROADMAP.md) — update
that file, not this one, when a phase moves. References here to "phase 4c" and the like
mean the phases defined there.

## Gotchas

### Environment and tooling

- `git status` on the Windows mount may show every file as modified (CRLF/LF). Check real
  diffs with `git -c core.autocrlf=input status`.
- The GitHub slug is `my_elt_project`; the local folder is still `my_etl_project`.
  Harmless; the `oidc.tf` sub claim is correct.
- The deploy `concurrency` group is not a queue: an intermediate push can be cancelled
  silently. Look here when asked "why didn't my commit ship".
- `.terraform.lock.hcl` carries hashes for one platform: never add `-lockfile=readonly`
  in CI (reason and fix: comment above `lint_tf` in the Makefile).
- `backend "s3"` uses `use_lockfile = true`; changing the backend block requires a one-off
  `terraform init -reconfigure` in an existing working copy.
- The `ci` target in `dbt_project/profiles.yml` is a deliberate dummy that only lets
  `dbt parse` render without secrets. Do not "fix" it to look like `dev` / `prod`.
- `docker-compose.override.yml` adds a local JupyterLab service (profile `local`).

### Silent failures

- **CI does not validate dbt SQL.** `dbt parse` builds the graph without executing SQL, so
  SQL errors and non-existent columns pass. Only a real `dbt build` sees them.
- **An empty prefix in `COPY INTO` is "zero files matched", not an error.** A typo in
  `s3_prefix` or a drifted date format is a silent no-op load. It is caught only by the
  next task, `dbt source freshness` on `_RAW_LOADED_AT` (warn 1h / error 3h) — that is a
  post-load assertion, not calendar freshness. Do not invent a separate check.
- **`AIRFLOW__SCHEDULER__CREATE_CRON_DATA_INTERVALS: 'true'` is load-bearing** (in
  `docker-compose.yml` and `ecs.tf`, reason in the `ecs.tf` comment). Removing it stops
  ingestion silently.
- An extract skip does not cancel the load (`NONE_FAILED_MIN_ONE_SUCCESS`, #43), but if
  every city skips, the load skips too. Do not add skip paths carelessly.
- `stg_openweather__weather` keeps only `weather[0]`; a second weather condition is
  dropped before any tested table exists.
- Marts LEFT JOIN `dim_location` on 4dp coordinates: a mismatch yields a NULL
  `location_id`, caught only by not_null / relationships on the marts.
- **The completeness test sees incomplete days but not absent ones** — a date with no rows
  forms no group. Catching missing dates needs a calendar (`dim_date`).
- **Green tests are not proven properties:** `unique` on `weather_id` would pass even
  without the dedup CTE on single-run data. dbt unit tests are the right tool there.

### Data correctness invariants

- **The warehouse was wiped 2026-08-15** (bronze in S3 and both RAW tables). History
  starts there, so "a full dbt build over all history is green" is true trivially, not
  proven at volume.
- Staging dedup orders by `_raw_loaded_at desc, _source_file desc`. `_RAW_LOADED_AT` is
  `SYSDATE()`, evaluated once per `COPY INTO`, so it ties within a run; the file name
  breaks the tie because the write-attempt timestamp sits left of the chunk index
  (ADR-0003). The goal is reproducible builds. Rationale repeated above each `qualify`.
- Boundary-hour duplicates in weather are fixed in the client (`< end_ts`); the staging
  dedup stays as protection against backfills and re-runs.
- `SnowflakeClient` interpolates the prefix into SQL as a string; it comes from
  `sources.yml` and `logical_date`, never from user input. No trailing slash: a
  `date=YYYY-MM-DD` prefix matches no other date.

## Known open defects

- **Two DAGs share part of the dbt graph and CAN race** (seed `cities_config`,
  `stg_internal__locations`, `dim_location`). Both are `@daily` with the same
  `start_date`; caught live as a doubled seed. Until fixed:
  - Do NOT make `stg_internal__locations` or `dim_location` tables — today only the
    atomicity of `create or replace view` protects them.
  - A green run is not a healthy run: retries hide the race, it shows only in
    `try_number`. Relevant to alerting (phase 4c).
  - Both processes share `target/` (no `--target-path`), and `max_active_runs` is unset,
    so a backfill collides with itself.
  - Agreed direction: seed out of the daily run (`--exclude tag:seed_layer`) into a
    manual DAG, and a per-run `--target-path` (not derived from `run_id`). No ADR — every
    part is revertible.
- The air-pollution client has the weather client's shape and was never checked for the
  boundary-hour duplication the weather client had.
- `terraform/database.tf`, `main.tf` and `oidc.tf` lack a trailing newline. Cosmetic;
  `fmt -check` does not flag it.
- The local `docker-compose.yml` has never been reviewed as a whole; findings are in
  `CLAUDE.local.md`.
