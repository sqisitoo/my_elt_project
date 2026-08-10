from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag, task

from plugins.common.config import settings
from plugins.common.utils.dbt import build_dbt_command

PLUGINS_DIR = "/opt/airflow/plugins"
# Lookup key into plugins/common/config/sources.yml — identifies which source
# configuration (target schema, table, S3 stage) to use during the load step.
SOURCE_NAME = "weather"


@dag(
    dag_id="weather_snowflake_dag",
    start_date=datetime(2026, 3, 10),
    schedule="@daily",
    catchup=False,
    template_searchpath=[PLUGINS_DIR],
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
)
def weather_snowflake_dag():
    """
    ELT pipeline that ingests historical weather data from OpenWeather into Snowflake.

    Flow:
        1. ``get_cities_config`` — load the list of cities to process from ``cities_config.csv``.
        2. ``extract_data`` — for each city, fetch weather data from the OpenWeather API and write
           the raw JSON payload to S3 (bronze layer), partitioned by city and date.
        3. ``load_to_snowflake`` — copy all files produced in the previous step from the
           S3 stage into the raw Snowflake table via ``COPY INTO``.
        4. ``run_dbt_source_freshness`` — assert that the source data meets freshness SLAs.
        5. ``run_dbt_build`` — build and test all dbt models downstream of the raw source.
    """

    @task
    def get_cities_config():
        from plugins.common.config.cities import get_cities_config

        cities = get_cities_config()

        return [city.model_dump() for city in cities]

    @task
    def extract_data(city_info: dict, logical_date, data_interval_start, data_interval_end):
        from airflow.providers.amazon.aws.hooks.s3 import S3Hook

        from plugins.common.clients.open_weather_client import OpenWeatherApiClient
        from plugins.common.clients.s3_client import S3Service
        from plugins.pipelines.weather_snowflake.extract import extract_weather_data
        from plugins.common.config.sources import get_source_config

        api_client = OpenWeatherApiClient(base_url=settings.api.url_str, api_key=settings.api.key)

        s3_hook = S3Hook(aws_conn_id="aws_default")
        boto3_client = s3_hook.get_conn()
        s3_service = S3Service(settings.aws.s3_bucket_name, s3_client=boto3_client)  # type: ignore

        source = get_source_config(SOURCE_NAME)
        s3_prefix = source.s3_prefix

        actual_datetime = datetime.now()

        s3_keys_to_raw_data = extract_weather_data(
            city=city_info["name"],
            lat=city_info["lat"],
            lon=city_info["lon"],
            open_weather_client=api_client,
            s3_service=s3_service,
            s3_prefix=s3_prefix,
            start_ts=data_interval_start.timestamp(),
            end_ts=data_interval_end.timestamp(),
            logical_date=logical_date,
            actual_datetime=actual_datetime,
        )

        return {"s3_keys_to_raw_data": s3_keys_to_raw_data, "city": city_info["name"]}

    @task
    def load_to_snowflake(extract_output_data):
        from plugins.common.clients.snowflake_client import SnowflakeClient
        from plugins.common.config.sources import get_source_config

        snowflake_client = SnowflakeClient(snowflake_conn_id="snowflake_conn")
        files = [key for r in extract_output_data for key in r["s3_keys_to_raw_data"]]
        source = get_source_config(SOURCE_NAME)

        snowflake_client.load_json_to_snowflake(
            file_names=files,
            s3_stage=source.s3_stage,
            target_schema=source.target_schema,
            target_table=source.target_table,
        )

    run_dbt_source_freshness = BashOperator(
        task_id="run_dbt_source_freshness",
        bash_command=build_dbt_command("source freshness", "source:openweather_weather"),
    )

    run_dbt_build = BashOperator(
        task_id="run_dbt_build", bash_command=build_dbt_command("build", "+fct_weather")
    )

    get_cities_config_task = get_cities_config()
    extract_tasks_group = extract_data.expand(city_info=get_cities_config_task)
    extract_tasks_group >> load_to_snowflake(extract_tasks_group) >> run_dbt_source_freshness >> run_dbt_build


weather_snowflake_dag()
