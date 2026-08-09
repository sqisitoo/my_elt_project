# ADR-0003: Immutable bronze — never overwrite or delete raw objects

## Status

Proposed — 2026-08-07

## Context

The completeness test on `fct_weather` reported 12 hourly rows instead of 24 for
one city on 2026-06-27. Tracing that number back through the layers turned up a
structural defect rather than a one-off.

Two objects sit under the partition prefix for that city and date:

| object | size | last modified (UTC) | present in RAW |
|---|---|---|---|
| `1782518400_part_1.json` | 3.6 KB | 2026-07-01 07:42 | yes |
| `1782518400_part_2.json` | 1.6 KB | 2026-06-28 22:11 | no |

`1782518400` is `int(logical_date.timestamp())` for 2026-06-27, so both objects
belong to the same logical date. Their modification times are 2.5 days apart,
which means two separate runs wrote into the same prefix: a first run produced
two chunks, a later re-run received less data from the API, produced one chunk,
overwrote `part_1` and returned a single key. `COPY INTO` is scoped to the keys
the run itself produced, so `part_2` was never offered to it and never loaded.

The root cause is that a bronze key is fully determined by city, `logical_date`
and chunk index. Two runs of the same logical date compete for the same object
names.

Underneath that sits the real problem. `RAW.WEATHER.RAW_WEATHER` is loaded with
`COPY INTO ... FILES = (...) FORCE = FALSE` and is never truncated, so it
accumulates the union of everything every run has ever loaded. S3 keeps only the
most recent version of each key. One collection only grows; the other is
overwritten in place. They cannot agree, and they currently do not: S3 holds 16
hours for that city and date, RAW holds 12.

Divergence runs in both directions and both are harmful. Objects present in S3
but absent from RAW mean a rebuild produces more than the pipeline did. Rows in
RAW whose source object has been overwritten mean a rebuild produces less, and
that data cannot be recovered from anywhere.

This breaks the one guarantee the bronze layer exists to provide: that every
layer below it can be rebuilt from it. The only reason to pay for storing raw
JSON in S3 at all is to have that recovery path; a path that cannot be trusted is
just a storage bill.

`air_pollution` carries the same defect in a quieter form. Its key is a single
object per city and logical date with no chunk index, so orphans cannot occur —
but a re-run still overwrites the object, and RAW still keeps what it loaded
earlier. Because Snowflake's load metadata is keyed on file path, a re-uploaded
object either loads a second time (RAW holds two versions, S3 one) or is skipped
as already loaded (RAW holds the old content, S3 the new). Either way the same
key name means different data in the two places, and nothing records it.

## Decision

Objects in the bronze layer are immutable. The pipeline never overwrites and
never deletes them.

To make that possible, every bronze key includes the moment the object was
written, so no two write attempts can collide on a name. Where one attempt
produces several objects, a chunk index disambiguates them and must appear to
the right of the timestamp. Both parts must sort chronologically, because the
staging deduplication uses `_source_file` as its tie-breaker. An identifier of
the run is not sufficient: clearing and re-running the same DAG run preserves
it, and re-running is precisely the repair path this decision has to survive.

This applies to both sources. `air_pollution` is in scope despite not exhibiting
orphans, because the underlying defect is identical and its symptoms are harder
to notice.

Bronze therefore grows monotonically, as does RAW, and the two agree by
construction rather than by care. Rebuilding RAW from S3 reproduces what the
pipeline accumulated.

Correcting data — choosing between versions, dropping duplicates, excluding known
bad records — happens in staging, which already deduplicates by surrogate key
ordered by `_raw_loaded_at desc, _source_file desc` and therefore prefers the
most recent run.

Removing objects from bronze is permitted only as an age-based bucket lifecycle
policy. Retention is a deliberate decision about cost, not a side effect of
re-running a DAG. No retention policy is decided here.

## Alternatives considered

**Delete leftover objects from the partition before or after writing.** This was
the first proposal and it is wrong. Deleting an object whose rows are already in
RAW moves the divergence to the direction that cannot be repaired: RAW then holds
data that exists nowhere else. Ordering the operations so that writes precede
deletes narrows the window but does not change the outcome, because the surplus
object was already loaded on an earlier run. It also required a new prefix-listing
and batch-delete method on `S3Service`, which is now unnecessary.

**Load every object under the partition prefix and let staging deduplicate, while
keeping mutable keys.** Closer, and it does make the load self-healing, but it
does not converge. Writing to a fixed key still destroys the previous version in
S3 while RAW retains the rows loaded from it. Concretely: a first run wrote 20
hours to `part_1` and 4 to `part_2`; a re-run overwrote `part_1` with 12 hours.
RAW holds the union — 24 distinct hours — while S3 can only reproduce 16. Loading
by prefix does not recover data that overwriting destroyed.

**Adopt a table format (Iceberg, Delta Lake, Hudi) for the raw zone.** These solve
exactly this problem in the general case: data files are never modified, new files
are added, and a manifest records which set is current. Rejected as
disproportionate. The property needed here is immutability, which a naming
convention delivers directly, and adopting a table format would introduce a
dependency and a body of operational knowledge that nothing else in the project
currently requires.

## Consequences

Storage grows with every re-run rather than being replaced. At current volumes —
five cities, kilobyte-scale objects, re-runs measured in single digits — this is
irrelevant, and the growth is bounded by whatever retention policy is chosen
later.

The staging deduplication changes role from a safety net to a load-bearing
component. It is already written correctly for this: `_raw_loaded_at` is set per
`COPY INTO` statement, so a later run carries a later value and wins. The
written-at timestamp in the key must be sortable and must precede the chunk index,
or the `_source_file` tie-breaker stops being meaningful for objects loaded within
a single statement.

Bad data can no longer be removed from bronze. A malformed API response is
preserved permanently and must be excluded downstream. This is the intended
property of a raw layer rather than a cost of this decision: bronze records what
arrived and does not judge it.

Objects written before this change remain in the old layout. The loader addresses
objects by explicit key and does not need to understand two layouts, so no
migration is required for the pipeline to keep working. A full rebuild from S3
over the pre-change history will still reproduce the old divergence, because that
history is genuinely lost. Deciding what to do about the existing data belongs to
the "clean data" roadmap step, not here.

One gap survives this decision. A run that writes objects to S3 and then fails
before loading them — the failure mode described in issue #43, where one skipped
mapped extract task skips the whole load — still leaves S3 ahead of RAW, and
those objects will never be offered to `COPY INTO` again. Immutable keys do not
address this. Loading by partition prefix instead of by an explicit `FILES` list
would make the load self-healing, since `FORCE = FALSE` skips what is already
loaded and picks up what was missed. That is a separate decision and is not made
here.

At a substantially larger number of cities the object-per-city-per-run layout runs
into Snowflake's preference for large files, and the design would shift toward
batching many cities into fewer, larger objects with the city moved into the
payload. Immutability is orthogonal to that change and would survive it.
