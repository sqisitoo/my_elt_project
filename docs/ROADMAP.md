# Roadmap

What remains to be done before the project is finished. History lives in git, decisions
in `docs/adr/`. When a step is done, delete it from this file.

## Finish line

The project is finished when five statements are true:

1. The README explains the project to an outsider without the author: purpose,
   architecture, how to run it, key decisions.
2. CI catches everything that today breaks silently: Python, the dbt project, Terraform.
3. The warehouse is clean: a full dbt build over the whole history is green, dev debris is
   cleared.
4. The pipeline is operated, not demonstrated: ≥2 weeks of runs, and a failure produces an
   alert rather than silence.
5. The infrastructure has no dead parts, warehouse layers are separated, dbt and Airflow
   are decoupled, and the existing Terraform survives a review.

Everything else is learning-debt: done after the finish line, and only if wanted.
Strategy: vertical slices — architectural debt is repaid when a phase runs into it.

## Phases

Phases 1–3 and step 4a are done; numbering is kept so references stay stable.

### 4. Infrastructure (cheapest step first)

- **4b. Separate warehouse layers** (#44, plus #24/#40 schema naming): no model writes
  into a neighbour's schema; the unused `ANALYTICS` database gets its role.
- **4c. Make failures visible: alerting** (#48). A test lives inside the DAG, so "the
  pipeline did not run at all" is caught by neither `source freshness` nor any mart test —
  only by an external observer. "The run was green" is not enough as a health criterion:
  a retried task hides a failure (see the two-DAG race in `CLAUDE.md`).
- **4d. Refactor the existing Terraform.** Done when `terraform/` contains no resource
  whose purpose and shape the owner cannot defend at review.
- **4e. Decouple dbt from Airflow** (they share one image today). The Cosmos question is
  settled here, as part of the same decision about how dbt is executed.
- **Postgres-ETL remnants in application code** (#45): requirements, `S3Service`,
  `_DBSettings`. Cheap; do alongside any step that touches them.

### 5. Operation

Let the project live for ≥2 weeks: green runs, at least one incident worked through. The
architecture diagram and an operations section go into the README.

**Precondition:** the completeness signal must be fit for daily reading. Today the
24-hours-per-day test checks the whole history, so the first unrecoverable gap turns it
permanently red. Split it into an archival test behind a tag (outside the daily run), a
daily test on a recent window, and a check that the latest `observation_utc_ts` is no
older than ~36h — the per-day test cannot see a day with no rows at all.

### 6. Consumption layer

Visualisation on top of the accumulated clean data. Finish.

## Deferred, not scheduled

- Split the dbt and Terraform checks into their own CI job (`needs:`), so they stop
  waiting ~3 minutes for Airflow dependencies. Do it when the wait gets annoying.

## Deliberately not doing

Kafka/streaming, Kubernetes, Great Expectations on top of dbt tests, the dbt Semantic
Layer, a third data source before the finish line.
