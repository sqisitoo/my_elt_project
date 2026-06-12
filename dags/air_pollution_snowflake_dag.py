from datetime import datetime, timedelta

from airflow.operators.bash import BashOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.sdk import dag, task

from plugins.common.config import settings
from plugins.common.utils.dbt import build_dbt_command

PLUGINS_DIR = "/opt/airflow/plugins"


@dag(
    dag_id="air_pollution_snowflake_dag",
    start_date=datetime(2026, 3, 10),
    schedule="@daily",
    catchup=False,
    template_searchpath=[PLUGINS_DIR],
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
)
def air_pollution_snowflake_dag():

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
        from plugins.pipelines.air_pollution_snowflake.extract import extract_air_pollution_to_s3

        api_client = OpenWeatherApiClient(base_url=settings.api.url_str, api_key=settings.api.key)

        s3_hook = S3Hook(aws_conn_id="aws_default")
        boto3_client = s3_hook.get_conn()
        s3_service = S3Service(settings.aws.s3_bucket_name, s3_client=boto3_client)  # type: ignore

        s3_key_to_raw_data = extract_air_pollution_to_s3(
            city=city_info["name"],
            lat=city_info["lat"],
            lon=city_info["lon"],
            logical_date=logical_date,
            open_weather_client=api_client,
            s3_service=s3_service,
            start_ts=data_interval_start.timestamp(),
            end_ts=data_interval_end.timestamp(),
        )

        return {"s3_key_to_raw_data": s3_key_to_raw_data, "city": city_info["name"]}

    load_raw_data = SQLExecuteQueryOperator(
        task_id="load_air_pollution_data",
        sql="pipelines/air_pollution_snowflake/sql/copy_air_pollution_data.sql",
        conn_id="snowflake_conn",
    )

    run_dbt_source_freshness = BashOperator(
        task_id="run_dbt_source_freshness",
        bash_command=build_dbt_command("source freshness"),
    )

    run_dbt = BashOperator(
        task_id="run_dbt",
        bash_command=build_dbt_command("build"),
    )

    get_cities_config_task = get_cities_config()
    extract_tasks_group = extract_data.expand(city_info=get_cities_config_task)

    extract_tasks_group >> load_raw_data >> run_dbt_source_freshness >> run_dbt


air_pollution_snowflake_dag()
