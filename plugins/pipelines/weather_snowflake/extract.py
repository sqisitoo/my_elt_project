import logging
from datetime import datetime

from airflow.exceptions import AirflowSkipException

from plugins.common.clients.open_weather_client import OpenWeatherApiClient
from plugins.common.clients.s3_client import S3Service
from plugins.common.utils.bronze_paths import object_key

logger = logging.getLogger(__name__)


def extract_weather_data(
    *,
    city: str,
    open_weather_client: OpenWeatherApiClient,
    s3_service: S3Service,
    s3_prefix: str,
    lat: float,
    lon: float,
    start_ts: int | float,
    end_ts: int | float,
    logical_date: datetime,
    actual_datetime: datetime,
) -> list[str]:
    """
    Extract historical weather data from OpenWeatherMap and upload to S3 (bronze layer).

    Iterates over paginated API responses (up to 20 hours per chunk) and uploads
    each chunk as a separate JSON file. Designed to be called inside an Airflow @task.

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
        List of S3 keys where data was uploaded. Downstream tasks can use these
        to locate the raw files for transformation.

    Raises:
        AirflowSkipException: If the API returned no data for the given range.
        requests.HTTPError: Propagated from the API client on non-2xx responses.
    """
    logger.info(
        f"Starting weather data extraction for {city} (lat={lat}, lon={lon}), range={start_ts}-{end_ts}"
    )

    s3_keys = []

    for ind, chunk in enumerate(
        open_weather_client.get_historical_weather_data(
            city=city, lat=lat, lon=lon, start_ts=start_ts, end_ts=end_ts
        )
    ):
        s3_key = object_key(
            s3_prefix=s3_prefix,
            logical_date=logical_date,
            actual_datetime=actual_datetime,
            city=city,
            part=ind + 1,
        )

        s3_service.save_dict_as_json(chunk, s3_key)
        s3_keys.append(s3_key)
        logger.info(f"Uploaded chunk {ind + 1} to {s3_key}")

    if not s3_keys:
        logger.warning(f"No weather data returned for {city} (lat={lat}, lon={lon})")
        raise AirflowSkipException(f"API returned no data for {city}, range={start_ts}-{end_ts}")

    logger.info(f"Extraction complete for {city}: {len(s3_keys)} chunk(s) uploaded")
    return s3_keys
