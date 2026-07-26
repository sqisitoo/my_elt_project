with staging_weather as (

    select
        weather_id,
        latitude,
        longitude,
        observation_utc_ts,
        cloudiness_percentage,
        temperature_celsius,
        temperature_feels_like_celsius,
        pressure_hPa,
        humidity_percentage,
        dew_point_temperature_celsius,
        uv_index,
        visibility_meter,
        wind_speed_metre_per_sec,
        wind_direction_degree,
        wind_gust_metre_per_sec,
        rain_1h_mm,
        snow_1h_mm,
        weather_description,
        weather_icon_id,
        weather_group,
        weather_condition_id
    from {{ ref('stg_openweather__weather') }}
),

location as (

    select
        location_id,
        latitude,
        longitude
    from {{ ref('dim_location') }}
),

joined as (

    select
        w.weather_id,
        l.location_id,
        w.observation_utc_ts,
        w.cloudiness_percentage,
        w.temperature_celsius,
        w.dew_point_temperature_celsius,
        w.pressure_hPa,
        w.humidity_percentage,
        w.uv_index,
        w.visibility_meter,
        w.wind_speed_metre_per_sec,
        w.wind_direction_degree,
        w.wind_gust_metre_per_sec,
        w.rain_1h_mm,
        w.snow_1h_mm,
        w.weather_condition_id

    from staging_weather w
    left join location l
    on w.latitude = l.latitude and w.longitude = l.longitude
)

select * from joined