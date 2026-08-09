from datetime import datetime, timezone
from unittest.mock import MagicMock, call

import pytest
from airflow.exceptions import AirflowSkipException

from plugins.pipelines.weather_snowflake.extract import extract_weather_data


@pytest.fixture
def mock_clients():
    """Returns a tuple of MagicMock objects for the OpenWeather client and S3 service."""
    return MagicMock(), MagicMock()


def test_extract_weather_data_single_chunk_success(mock_clients):
    """
    Test that extract_weather_data uploads a single chunk to S3 and returns the correct key.
    """
    mock_open_weather_client, mock_s3_service = mock_clients

    city = "Berlin"
    logical_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    actual_datetime = datetime(2025, 1, 1, 0, 5, 0, tzinfo=timezone.utc)
    chunk = {"dt": 1735689600, "temp": 5.0}
    mock_open_weather_client.get_historical_weather_data.return_value = [chunk]

    expected_key = (
        f"bronze/weather_data/"
        f"city={city}/"
        f"year={logical_date.year}/"
        f"month={logical_date.month:02d}/"
        f"day={logical_date.day:02d}/"
        f"{logical_date.strftime('%Y%m%d%H%M%S')}_{actual_datetime.strftime('%Y%m%d%H%M%S')}_part_1.json"
    )

    result = extract_weather_data(
        city=city,
        open_weather_client=mock_open_weather_client,
        s3_service=mock_s3_service,
        lat=52.5,
        lon=13.4,
        start_ts=1735689600,
        end_ts=1735776000,
        logical_date=logical_date,
        actual_datetime=actual_datetime,
    )

    assert result == [expected_key]
    mock_s3_service.save_dict_as_json.assert_called_once_with(chunk, expected_key)


def test_extract_weather_data_multiple_chunks_success(mock_clients):
    """
    Test that extract_weather_data uploads each chunk with the correct part number in the S3 key
    and returns all keys in order.
    """
    mock_open_weather_client, mock_s3_service = mock_clients

    city = "Berlin"
    logical_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    actual_datetime = datetime(2025, 1, 1, 0, 5, 0, tzinfo=timezone.utc)
    chunks = [{"dt": 1735689600}, {"dt": 1735693200}, {"dt": 1735696800}]
    mock_open_weather_client.get_historical_weather_data.return_value = chunks

    expected_keys = [
        (
            f"bronze/weather_data/"
            f"city={city}/"
            f"year={logical_date.year}/"
            f"month={logical_date.month:02d}/"
            f"day={logical_date.day:02d}/"
            f"{logical_date.strftime('%Y%m%d%H%M%S')}_{actual_datetime.strftime('%Y%m%d%H%M%S')}_part_{i}.json"
        )
        for i in range(1, 4)
    ]

    result = extract_weather_data(
        city=city,
        open_weather_client=mock_open_weather_client,
        s3_service=mock_s3_service,
        lat=52.5,
        lon=13.4,
        start_ts=1735689600,
        end_ts=1735776000,
        logical_date=logical_date,
        actual_datetime=actual_datetime,
    )

    assert result == expected_keys
    assert mock_s3_service.save_dict_as_json.call_count == 3
    mock_s3_service.save_dict_as_json.assert_has_calls(
        [
            call(chunks[0], expected_keys[0]),
            call(chunks[1], expected_keys[1]),
            call(chunks[2], expected_keys[2]),
        ]
    )


def test_extract_weather_data_raises_skip_exception_on_empty_data(mock_clients):
    """
    Test that extract_weather_data raises AirflowSkipException and does not upload to S3
    when the API returns no chunks.
    """
    mock_open_weather_client, mock_s3_service = mock_clients
    mock_open_weather_client.get_historical_weather_data.return_value = []

    logical_date = datetime(2025, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(AirflowSkipException):
        extract_weather_data(
            city="Berlin",
            open_weather_client=mock_open_weather_client,
            s3_service=mock_s3_service,
            lat=52.5,
            lon=13.4,
            start_ts=1735689600,
            end_ts=1735776000,
            logical_date=logical_date,
            actual_datetime=datetime(2025, 1, 1, 0, 5, 0, tzinfo=timezone.utc),
        )

    mock_s3_service.save_dict_as_json.assert_not_called()
