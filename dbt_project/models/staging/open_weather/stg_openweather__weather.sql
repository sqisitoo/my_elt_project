with source as (

    select raw_payload, _source_file, _raw_loaded_at
    from {{ source('openweather', 'raw_weather') }}

),

flattened as (
    
    select
        raw_payload:lat::float as latitude,
        raw_payload:lon::float as longitude,

        to_timestamp_ntz(f.value:dt::number) as observation_utc_ts,

        try_cast(f.value:clouds::string as number) as cloudiness_percentage,
        try_cast(f.value:temp::string as float) as temperature_celsius,
        try_cast(f.value:feels_like::string as float) as temperature_feels_like_celsius,
        try_cast(f.value:pressure::string as number) as pressure_hPa,
        try_cast(f.value:humidity::string as number) as humidity_percentage,
        try_cast(f.value:dew_point::string as float) as dew_point_temperature_celsius,
        try_cast(f.value:uvi::string as float) as uv_index,
        try_cast(f.value:visibility::string as number) as visibility_meter,
        try_cast(f.value:wind_speed::string as float) as wind_speed_metre_per_sec,
        try_cast(f.value:wind_deg::string as number) as wind_direction_degree,
        try_cast(f.value:wind_gust::string as float) as wind_gust_metre_per_sec,
        try_cast(f.value:rain."1h"::string as float) as rain_1h_mm,
        try_cast(f.value:snow."1h"::string as float) as snow_1h_mm,
        f.value:weather[0].description::string as weather_description,
        f.value:weather[0].icon::string as weather_icon_id,
        f.value:weather[0].main::string as weather_group,
        try_cast(f.value:weather[0].id::string as number) as weather_condition_id,
        _source_file,
        _raw_loaded_at,
        '{{ run_started_at }}'::timestamp_tz as _stg_loaded_at
    from source
    lateral flatten(input => raw_payload:data) f
),

rounded as (
    select
        round(latitude, 4) as latitude,
        round(longitude, 4) as longitude,

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
        weather_condition_id,
        _source_file,
        _raw_loaded_at,
        _stg_loaded_at
    from flattened
),

hashed as (
    select
        {{ dbt_utils.generate_surrogate_key([
            'latitude', 
            'longitude', 
            'observation_utc_ts'
        ]) }} as weather_id,
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
        weather_condition_id,
        _source_file,
        _raw_loaded_at,
        _stg_loaded_at
    from rounded
),

final as (
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
        weather_condition_id,
        _source_file,
        _raw_loaded_at,
        _stg_loaded_at
    from hashed
)

select * from final
