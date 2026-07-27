-- Data-quality contract: fct_weather must contain one observation per location
-- per UTC hour. A complete UTC day therefore has exactly 24 observations.
-- Missing or duplicate hours make daily aggregates and cross-day comparisons
-- unreliable: averages use an incomplete sample, totals can be understated, and
-- hourly extremes may be missed.
with daily_counts as (
    select
        location_id,
        date(observation_utc_ts) as obs_date,
        count(*) as hourly_records_count
    from {{ ref('fct_weather') }}
    group by location_id, obs_date
)

select location_id, obs_date, hourly_records_count
from daily_counts
-- The 24-hour expectation is valid because observations are grouped by UTC date.
-- A local-time grouping would legitimately have 23 or 25 hours on daylight-saving
-- time transition days.
where hourly_records_count != 24 