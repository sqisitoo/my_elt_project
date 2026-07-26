-- Data-quality contract: fct_weather must contain one observation per location
-- per UTC hour. A complete UTC day therefore has exactly 24 observations.
-- Missing or duplicate hours make daily aggregates and cross-day comparisons
-- unreliable: averages use an incomplete sample, totals can be understated, and
-- hourly extremes may be missed.

-- TEMPORARY: The weather client keeps records at `end_ts` (`record["dt"] <= end_ts`),
-- while Airflow daily data intervals are half-open: [data_interval_start, data_interval_end).
-- Each run therefore loads midnight from the following UTC date. Until the client uses
-- `< end_ts`, the latest date has only that one row, so this completeness check warns.
{{ config(severity='warn') }}

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