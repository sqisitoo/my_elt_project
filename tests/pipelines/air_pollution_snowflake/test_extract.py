from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from airflow.exceptions import AirflowSkipException

from plugins.pipelines.air_pollution_snowflake.extract import extract_air_pollution_to_s3


@pytest.fixture
def record_raw():
    """Returns a single record raw."""
    return {
        "dt": 1606482000,
        "main": {"aqi": 2},
        "components": {
            "co": 200.0,
            "no": 10.0,
            "no2": 10.0,
            "o3": 10.0,
            "so2": 10.0,
            "pm2_5": 10.0,
            "pm10": 10.0,
            "nh3": 10.0,
        },
    }


@pytest.fixture
def mock_clients():
    """
    Fixture that returns a tuple of MagicMock objects to mock the OpenWeather client and S3 service.
    """
    return MagicMock(), MagicMock()


def test_extract_air_pollution_to_s3_success_path(mock_clients, record_raw):
    """
    Test that extract_air_pollution_to_s3  saves data to S3 and returns the correct key when data is present.
    """
    mock_open_weather_client, mock_s3_service = mock_clients

    # Prepare fake data and expected S3 key
    fake_data, city = {"coord": {"lon": 50.0, "lat": 50.0}, "list": [record_raw] * 24}, "Berlin"
    logical_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    run_id = "manual__2025-01-01T00:00:00+00:00"
    expected_key = (
        f"bronze/air_pollution/"
        f"city={city}/"
        f"year={logical_date.year}/"
        f"month={logical_date.month:02d}/"
        f"day={logical_date.day:02d}/"
        f"run_id={run_id}/"
        f"{int(logical_date.timestamp())}.json"
    )

    # Mock the OpenWeather client to return fake data
    mock_open_weather_client.get_historical_airpollution_data.return_value = fake_data

    # Call the function under test
    result_key = extract_air_pollution_to_s3(
        city=city,
        open_weather_client=mock_open_weather_client,
        s3_service=mock_s3_service,
        lat=50.0,
        lon=50.0,
        start_ts=120000,
        end_ts=130000,
        logical_date=logical_date,
        run_id=run_id,
    )

    # Assert the returned key matches the expected key
    assert result_key == expected_key

    # Assert that the S3 service was called to save the data
    expected_dict = fake_data
    mock_s3_service.save_dict_as_json.assert_called_once_with(expected_dict, result_key)

    # Unpack call_args: args=positional args tuple, _=kwargs (ignored)
    args, _ = mock_s3_service.save_dict_as_json.call_args
    saved_data = args[0]
    assert len(saved_data["list"]) == 24


def test_extract_air_pollution_to_s3_raises_skip_exception_on_empty_data(mock_clients):
    """
    Test that extract_air_pollution_to_s3 skips processing and does not write to S3
    when no records are returned.
    """
    mock_open_weather_client, mock_s3_service = mock_clients
    mock_open_weather_client.get_historical_airpollution_data.return_value = {"list": []}

    logical_date = datetime(2025, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(AirflowSkipException):
        extract_air_pollution_to_s3(
            city="Berlin",
            open_weather_client=mock_open_weather_client,
            s3_service=mock_s3_service,
            lat=50.0,
            lon=50.0,
            start_ts=120000,
            end_ts=130000,
            logical_date=logical_date,
            run_id="manual__2025-01-01T00:00:00+00:00",
        )

    mock_s3_service.save_dict_as_json.assert_not_called()
