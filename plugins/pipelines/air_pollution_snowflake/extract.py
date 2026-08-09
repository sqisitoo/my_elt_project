import logging
from datetime import datetime

from airflow.exceptions import AirflowSkipException

from plugins.common.clients.open_weather_client import OpenWeatherApiClient
from plugins.common.clients.s3_client import S3Service

logger = logging.getLogger(__name__)


def extract_air_pollution_to_s3(
    *,
    city: str,
    open_weather_client: OpenWeatherApiClient,
    s3_service: S3Service,
    lat: float,
    lon: float,
    start_ts: int | float,
    end_ts: int | float,
    logical_date: datetime,
    actual_datetime: datetime
) -> str:
    """
    Extract historical air pollution data from OpenWeatherMap and upload to S3 (bronze layer).

    Calls OpenWeather's historical API for the requested time window, validates
    that at least one record was returned, and uploads the raw payload as a
    single JSON file. Designed to be called inside an Airflow @task.

    Args:
        city: City name used for logging and S3 partitioning.
        open_weather_client: Configured OpenWeatherMap API client.
        s3_service: S3 client for uploading raw data.
        lat: Latitude of the target location.
        lon: Longitude of the target location.
        start_ts: Start of the extraction window (Unix timestamp).
        end_ts: End of the extraction window (Unix timestamp).
        logical_date: Airflow logical date, used to build the S3 partition path.
        actual_datetime: Wall-clock time of the extract call, used to disambiguate S3 keys across re-runs.

    Returns:
        S3 key where data was uploaded. Downstream tasks can use it to locate
        the raw file for transformation.

    Raises:
        AirflowSkipException: If the API response does not contain any records.
        requests.HTTPError: Propagated from the API client on non-2xx responses.
    """
    # Pull raw historical records for the requested city and time window.
    data = open_weather_client.get_historical_airpollution_data(
        city=city, lat=lat, lon=lon, start_ts=start_ts, end_ts=end_ts
    )

    raw_list = data.get("list")

    # Skip downstream work when the upstream API has no records.
    if not raw_list:
        logger.warning(f"API returned empty result for lat:{lat}, lon:{lon}")
        raise AirflowSkipException(f"API returned empty list for lat:{lat}, lon:{lon}")

    logger.info(f"Retrieved {len(raw_list)} raw records from API")

    logical_ts_nodash = logical_date.strftime('%Y%m%d%H%M%S')
    actual_ts_nodash = actual_datetime.strftime('%Y%m%d%H%M%S')

    # Build a partitioned bronze key for traceable and query-friendly storage.
    s3_key = (
        f"bronze/air_pollution/"
        f"city={city}/"
        f"year={logical_date.year}/"
        f"month={logical_date.month:02d}/"
        f"day={logical_date.day:02d}/"
        f"{logical_ts_nodash}_{actual_ts_nodash}.json"
    )

    s3_service.save_dict_as_json(data, s3_key)
    logger.info(f"Successfully saved data to S3: {s3_key}")
    return s3_key
