# ADR-0002: Measure completeness testing policy

## Status

Accepted — decided 2026-07-28, recorded 2026-07-30 (see ADR-0001, Consequences)

## Context

Completeness testing across the staging models had drifted into two incompatible
shapes. `stg_openweather__air_quality` carried no `not_null` tests on its measures
at all. `stg_openweather__weather` carried `not_null` on some measures, and on
five of them — `temperature_feels_like_celsius`, `dew_point_temperature_celsius`,
`uv_index`, `visibility_meter`, `wind_direction_degree` — with
`severity: warn`. The warn markers had been added a week earlier with no recorded
reason, and I could no longer reconstruct one.

Two problems sat underneath the drift.

First, `not_null` and range tests had been treated as one tool, "checking a
measure". They answer different questions. A range test asserts correctness: if a
value arrived, it must be sane. `not_null` asserts completeness: a value was
required to arrive. Completeness is a claim about the *source contract*, not
about the data — and a claim about the source needs evidence.

Second, the descriptions and the tests disagreed. The five warn columns had tests
tolerating NULLs while their documentation said nothing about NULLs being
possible, so a consumer reading "Non-additive: use AVG or MAX" had no way to know
the average would be computed over an incomplete sample.

Evidence gathered before deciding: NULL counts per column were queried directly in
Snowflake across all loaded data. No NULLs were found in any measure other than
`rain_1h_mm`, `snow_1h_mm` and `wind_gust_metre_per_sec`.

## Decision

Every column falls into exactly one of three categories.

**Structural** — grain columns and keys. `not_null` at default severity. A NULL
here breaks the grain itself.

**Measures the source is required to always return.** `not_null` at default
severity. A NULL here means the extractor broke or the API changed; it is an
incident, not a property of the weather.

**Measures whose absence is a legitimate state** — currently `rain_1h_mm`,
`snow_1h_mm`, `wind_gust_metre_per_sec`. No `not_null`. Instead the column
description is *required* to state what NULL means there: for rain and snow it
means "none was reported", not "unknown", and the two readings imply different
handling downstream.

Any deviation from default severity requires an adjacent comment giving the
reason and the condition under which it is removed. A test whose justification is
not written down is superstition, and a permanently yellow test is one nobody
reads.

Category membership is decided from data and source documentation, not intuition.

## Alternatives considered

**Drop `not_null` from all measures, keep only range tests.** This was the
initially attractive option, since no NULLs had been observed. Rejected on the
grounds that "no NULLs observed" is the argument *for* asserting the field is
mandatory, not against it: the assertion is what turns a silent absence into a
loud failure. Without it, a source change that starts omitting a field would
produce quietly incomplete aggregates.

**Keep `severity: warn` as a hedge where confidence was low.** Rejected: a warn
that fires on every scheduled run is invisible, and it trains the reader to skim
past neighbouring results. Warn has exactly one honest use — a temporary marker
with a written reason and a removal condition, as was done with the
24-hour completeness test while the client-side boundary-hour bug was open.

**Assert NULL-rate thresholds instead of binary `not_null`** (for example
`dbt_utils.not_null_proportion` with `min_proportion`). Rejected for now, not on
principle — for measures that are usually-but-not-always present this is the
better instrument. A threshold requires a baseline, and the warehouse currently
holds development data with missing dates and partial days. Any percentage chosen
today would be invented, and an invented threshold eventually fires on legitimate
data and gets switched off. Revisit after the warehouse is cleaned and roughly a
month of clean runs has accumulated.

## Consequences

Both source families now follow one rule, and every `not_null` in the project
traces back to either a structural role or an observed source behaviour.

The category-2 assertions rest on a sample drawn from a period with known gaps.
If OpenWeather omits one of those fields under conditions absent from that
sample, the DAG will fail. This is the accepted direction of failure: loud and
immediate rather than silent and cumulative.

Such a failure is evidence about the source contract, not automatically a bug to
suppress. The correct response is to confirm the condition against the API
documentation, move the column to category 3, and document what NULL means there
— not to lower severity.

Because the categories are recorded here rather than only in the yml files, a
future change that adds `severity: warn` without a reason is visibly a deviation
from a stated policy rather than a plausible-looking local choice.
