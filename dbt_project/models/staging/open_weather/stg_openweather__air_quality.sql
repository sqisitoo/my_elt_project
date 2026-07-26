with source as (

    select raw_payload, _source_file, _raw_loaded_at
    from {{ source('openweather_air_pollution', 'raw_air_pollution') }}

),

flattened as (

    select
        raw_payload:coord.lat::float as latitude,
        raw_payload:coord.lon::float as longitude,
        
        to_timestamp_ntz(f.value:dt::number) as observation_utc_ts,

        f.value:main.aqi::int as aqi,

        -- safe cast
        try_cast(f.value:components.co::string as float) as co,
        try_cast(f.value:components.no::string as float) as no,
        try_cast(f.value:components.no2::string as float) as no2,
        try_cast(f.value:components.o3::string as float) as o3,
        try_cast(f.value:components.so2::string as float) as so2,
        try_cast(f.value:components.pm2_5::string as float) as pm2_5,
        try_cast(f.value:components.pm10::string as float) as pm10,
        try_cast(f.value:components.nh3::string as float) as nh3,

        _source_file,
        _raw_loaded_at,
        '{{ run_started_at }}'::timestamp_tz as _stg_loaded_at
    from source,
    lateral flatten(input => raw_payload:list) f

),

rounded as (
    select
        round(latitude, 4) as latitude,
        round(longitude, 4) as longitude,

        observation_utc_ts,
        aqi,
        co,
        no,
        no2,
        o3,
        so2,
        pm2_5,
        pm10,
        nh3,
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
        ]) }} as air_quality_id,

        latitude,
        longitude,
        observation_utc_ts,
        aqi,
        co,
        no,
        no2,
        o3,
        so2,
        pm2_5,
        pm10,
        nh3,
        _source_file,
        _raw_loaded_at,
        _stg_loaded_at
    from rounded
),

deduplicated as (
    select
        air_quality_id,
        latitude,
        longitude,
        observation_utc_ts,
        aqi,
        co,
        no,
        no2,
        o3,
        so2,
        pm2_5,
        pm10,
        nh3,
        _source_file,
        _stg_loaded_at
    from hashed
    -- _raw_loaded_at is identical for all rows in one COPY INTO because it defaults to SYSDATE(), so this tie-breaker is effective.
    -- Source file names encode logical_date and part number, so a lexicographically larger name represents a later load.
    -- The goal is reproducible builds, not a "correct" row: versions with equal load times are equally fresh.
    qualify row_number() over (
        partition by air_quality_id
        order by _raw_loaded_at desc, _source_file desc
    ) = 1
),

final as (
    
    select

        air_quality_id,
        latitude,
        longitude,
        observation_utc_ts,
        aqi,
        co,
        no,
        no2,
        o3,
        so2,
        pm2_5,
        pm10,
        nh3,
        
        _source_file,
        _stg_loaded_at
        
    from deduplicated      
)

select * from final