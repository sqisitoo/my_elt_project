with staging_air as (
    select
        air_quality_id,
        latitude,
        longitude,
        observation_ts,
        aqi,
        co,
        no,
        no2,
        o3,
        so2,
        pm2_5,
        pm10,
        nh3
    from {{ ref('stg_openweather__air_quality') }}
),

dim_loc as (
    select
        location_id,
        city_name,
        latitude,
        longitude
    from {{ ref('dim_location') }}
),

joined as (
    select
        s.air_quality_id,
        l.location_id,
        s.observation_ts,
        s.aqi,
        s.co,
        s.no,
        s.no2,
        s.o3,
        s.so2,
        s.pm2_5,
        s.pm10,
        s.nh3
    from  staging_air s
    left join dim_loc l
    on s.latitude = l.latitude and s.longitude = l.longitude
)

select * from joined