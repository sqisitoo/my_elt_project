# ADR-0004: Load by partition prefix, not by an explicit file list

## Status

Accepted — 2026-08-10 (proposed 2026-08-09)

## Context

ADR-0003 made bronze immutable: objects are never overwritten and never deleted,
and every key carries the moment it was written. A partition prefix is therefore
a stable, monotonically growing description of everything the pipeline has ever
collected for that city and date.

The loader has not caught up with that. `COPY INTO` is scoped to
`FILES = (...)`, a list of the keys the current run produced, passed from the
extract tasks through XCom. That list answers "what did this run write", while
the question the load has to answer is "what is in bronze that is not yet in
RAW". The two coincide only when every run succeeds.

They diverge in a failure mode that already exists. An extract task writes its
objects to S3 and the load never runs — because a mapped extract for one city
raised `AirflowSkipException`, and the default trigger rule treats a skipped
upstream as reason enough to skip the load (issue #43). The objects are on S3,
the keys are gone with the run, and nothing will ever offer them to `COPY INTO`
again. ADR-0003 named this gap explicitly and left it open; this is where it gets
closed.

The dependency also runs the wrong way. Because the load consumes the extract's
return value, it is coupled to the extract as data, not merely as ordering. That
is what makes a single quiet city capable of skipping the entire load rather
than reducing it.

Two properties of the current system bound how much machinery this deserves.
Volumes are tiny — five cities, kilobyte-scale JSON, one run a day. And staging
already deduplicates by surrogate key, a role ADR-0003 promoted from safety net
to load-bearing, so loading the same object twice costs storage and nothing else.
The requirement is therefore not exactly-once delivery. It is that nothing in
bronze stays permanently invisible to RAW.

## Decision

`COPY INTO` addresses the partition prefix for the logical date being processed,
rather than a list of keys. Snowflake's load metadata decides what is new:
`FORCE = FALSE` skips objects already loaded into the target table, and
`LOAD_UNCERTAIN_FILES = TRUE` allows objects whose load metadata has expired to
be attempted rather than silently skipped.

For a prefix to address a date at all, the bronze layout puts the date above the
city. This is part of the same decision rather than a separate one: a load scoped
to a prefix is only as useful as the prefixes the layout can express.

Completeness is not guaranteed by construction. It is asserted by tests and
repaired by re-running the DAG for the affected date, which re-reads the same
prefix and picks up any object stranded by an earlier failure — including objects
written by runs that never reached the load step. The strategy is deliberately
"detect and repair" rather than self-healing, because detection is needed anyway
and repair is a single re-run.

With the key list gone, the load no longer consumes anything the extract
produces. It depends on the extracts only for ordering, so its trigger rule
changes to one that tolerates skipped upstreams, and a single city returning no
data stops cancelling the load for the other four. This closes #43 as a
consequence of the change rather than as separate work.

## Alternatives considered

**Keep the explicit `FILES` list.** Rejected for the reasons in Context: it
describes the run rather than the gap between bronze and RAW, and it is precisely
what strands objects when a run dies between writing and loading.

**Snowpipe with auto-ingest.** S3 event notifications drive loading, and the
question of what to load disappears. Rejected for now, not on merit: it requires
infrastructure that does not exist yet (a pipe, an SQS queue, IAM wiring, all in
Terraform), and it makes loading asynchronous, so the DAG can no longer tell
whether the data arrived. Its own load history is also shorter — fourteen days
rather than sixty-four. This is the natural destination if loading is ever
decoupled from the orchestrator, and it should be reconsidered then rather than
rediscovered.

**A registry of loaded objects, maintained by us.** RAW already records
`_SOURCE_FILE` for every row, so the set of loaded objects is known exactly and
permanently; the objects to load are the difference between an S3 listing and
that set. This is more precise than load metadata and immune to its expiry.
Rejected because it buys precision the current volumes do not need, at the cost
of code that has to be correct about partial failures — while `FORCE = FALSE`
provides the same idempotency for free.

**A directory table on the external stage.** The same difference, computed
entirely inside Snowflake. Rejected for the same reason, plus it needs its own
refresh mechanism to stay accurate.

**An external table over bronze, or a table format such as Iceberg.** Loading
stops existing as a step; RAW becomes a view over S3. Rejected as
disproportionate, consistent with ADR-0003. It would also remove
`_RAW_LOADED_AT`, which the staging deduplication orders by, so the change is
larger than it first appears.

**`FORCE = TRUE`, letting staging deduplicate.** Defensible at this scale, since
duplicates in RAW are invisible below staging. Rejected because RAW would then
grow with every run regardless of whether anything new arrived, and load metadata
already prevents that at no cost.

## Consequences

Repair becomes an operation the pipeline supports rather than a manual query:
re-run the date. Anything under the prefix that RAW is missing is picked up,
whatever the reason it was missed.

Self-healing has a shelf life of sixty-four days, which is how long Snowflake
keeps load metadata for a table. Beyond that the answer to "was this loaded" is
no longer definitive, and `LOAD_UNCERTAIN_FILES = TRUE` resolves the doubt in
favour of loading. Objects re-loaded that way produce duplicate rows in RAW,
which staging removes. This is the intended trade: recoverability of old data in
exchange for duplicates that are already handled.

Because the load no longer knows which objects belong to the current run,
nothing in the pipeline verifies that what was extracted is what was loaded.
Data completeness is now entirely a property that tests observe after the fact,
which raises the stakes on the completeness signal being readable day to day —
`assert_fct_weather_has_24_hours_per_location_day`, the only test that measures
it, inspects the whole history on every run and will be permanently red as soon
as one unrecoverable gap exists.

The bronze layout changes so that the date sits above the city, and the date
becomes one path segment rather than three:

    bronze/weather/date=2026-06-27/city=Warsaw/<logical_ts>_<actual_ts>_part_1.json

The root of that path — `bronze/weather`, `bronze/air_pollution` — moves into the
source registry (`plugins/common/config/sources.yml`, field `s3_prefix`), because
it is now read by two parties rather than one: the extract writes under it and the
load copies from under it. The date segment stays in code, in a single function
that both parties call, so the two cannot disagree about its format. The weather
root is renamed from `bronze/weather_data` to `bronze/weather` while renaming is
still free, so roots match the keys of the registry entries.

A single segment keeps a range of dates expressible as a string comparison,
because this format sorts chronologically. Splitting it into `year=/month=/day=`
would buy whole-month and whole-year prefixes, which nothing in this project asks
for, at the cost of turning every range into a disjunction across month and year
boundaries — the form that typically defeats partition pruning in engines reading
the bucket, and that turns "which dates exist" from one delimited listing into a
three-level walk. The `key=value` convention is kept so partition columns stay
self-describing.

Loading a date is then a single prefix and a single `COPY INTO`, instead of one
statement per city;
the same asymmetry applies to every other operation addressed by time, which is
nearly all of them — backfilling a range, listing what exists for a date during an
incident, expiring old data. The reverse question, "the whole history of one
city", becomes expensive and has no known caller: nothing reads the city out of
the key. It is written by the extract functions and read by no model, no test and
no join — staging matches a row to a location by coordinates from the payload,
and the API response does not carry the city name at all. The city segment
therefore exists purely for human navigation and can sit anywhere.

Changing the layout is free only right now. No code parses the key, so no model
or test is affected; the deduplication tie-break is unaffected because it only
ever compares rows sharing a surrogate key, which means the same coordinates and
therefore the same city, so the differing part of the two paths remains the
filename; and the warehouse cleanup removes the pre-existing objects anyway, so
no migration and no period of two coexisting layouts. Once new history starts
accumulating under the current layout, none of that stays true.

`ON_ERROR = 'ABORT_STATEMENT'` becomes riskier in combination with immutable
bronze. A malformed object can no longer be deleted, so it will fail every load
that touches its prefix, indefinitely, rather than once. The setting is left as
it is for now, and not only because the data is small enough to inspect by hand.
The pipeline is still under development and has no downstream consumers, so
nothing is lost by stopping it, while a silent skip would leave the decision of
whether to investigate up to me. A failing load makes that investigation
mandatory rather than merely advisable, which is the right default while I am
still learning what this pipeline does wrong. The first malformed object forces
a real decision, and it should be made then, with the object in hand.

Everything already in bronze becomes invisible to the loader. Existing objects
were written under the old layout, which puts the city above a three-segment date
and, for weather, under a different root — so none of them sits under any prefix
the new load addresses. They are neither re-loaded nor repaired; whatever of that
history reached RAW stays there until the warehouse cleanup removes both sides.
This is acceptable only because that cleanup is the next step and the history is
dev debris.

Listing cost grows with the number of objects under one prefix, which is bounded
by a single day, so it does not grow over time. A layout change that widened the
prefix — or a decision to load the whole bronze tree — would remove that bound.
