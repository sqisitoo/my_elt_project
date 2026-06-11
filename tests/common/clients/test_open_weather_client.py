from typing import Any
from urllib.parse import urljoin

import pytest
import requests
import requests_mock
from pydantic import SecretStr
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from plugins.common.clients.open_weather_client import ENDPOINTS, OpenWeatherApiClient


@pytest.fixture
def base_url():
    # Root URL used to initialise the client; does not include any endpoint path.
    return "http://api.test.com/data"


@pytest.fixture
def historical_airpollution_url(base_url):
    # Full URL for the air-pollution history endpoint, built the same way the client does.
    # Used as the mock target so tests always stay in sync with the real URL construction logic.
    return urljoin(base_url, ENDPOINTS["historical_airpollution_data"])


@pytest.fixture
def historical_weather_url(base_url):
    # Full URL for the historical weather timeline endpoint.
    return urljoin(base_url, ENDPOINTS["historical_weather_data"])


@pytest.fixture
def api_key():
    # Dummy API key wrapped in SecretStr, matching the type the client expects.
    return SecretStr("secret_api_key")


@pytest.fixture
def client(base_url, api_key):
    # Provides a fully initialised client for each test; session is closed on teardown
    # so open connections don't leak between tests.
    client_instance = OpenWeatherApiClient(base_url, api_key)

    yield client_instance

    client_instance.session.close()


@pytest.fixture
def mock_requests():
    # Intercepts all outbound HTTP calls for the duration of the test.
    # Any request to an unregistered URL raises NoMockAddress, preventing real network calls.
    with requests_mock.Mocker() as m:
        yield m


def test_endpoints_contract():
    # Contract test: any change to ENDPOINTS keys or values will fail here explicitly,
    # making the breakage obvious before other tests start failing with NoMockAddress errors.
    assert ENDPOINTS == {
        "historical_airpollution_data": "/data/2.5/air_pollution/history",
        "historical_weather_data": "/data/4.0/onecall/timeline/1h",
    }


def test_full_url_construction(client, mock_requests, historical_airpollution_url):
    # Verifies that the client assembles the correct full URL from base_url and the endpoint path.
    # If urljoin behaviour changes or the endpoint key is wrong, this test fails with a clear message
    # before the other tests fail with NoMockAddress.
    mock_requests.get(historical_airpollution_url, json={}, status_code=200)

    client.get_historical_airpollution_data(city="Test", lat=0, lon=0, start_ts=0, end_ts=0)

    assert mock_requests.last_request.path == ENDPOINTS["historical_airpollution_data"]


def test_get_historical_data_success_params(client, historical_airpollution_url, api_key, mock_requests):
    # Happy path: verifies that all query params are sent correctly and the response is returned as-is.
    mock_response = {"list": [{"dt": 228}]}

    mock_requests.get(historical_airpollution_url, json=mock_response, status_code=200)

    result = client.get_historical_airpollution_data(
        city="TestCity", lat=10.5, lon=20.5, start_ts=10000, end_ts=20000
    )

    assert result == mock_response

    assert mock_requests.called
    assert mock_requests.call_count == 1
    assert mock_requests.last_request.method == "GET"

    query_string = mock_requests.last_request.qs

    assert query_string["lat"] == ["10.5"]
    assert query_string["lon"] == ["20.5"]
    assert query_string["start"] == ["10000"]
    assert query_string["end"] == ["20000"]
    assert query_string["appid"] == [api_key.get_secret_value()]


def test_retry_strategy_configuration(client):
    # Checks the retry adapter is mounted with the expected parameters on both http:// and https://.
    # This is a unit test of __init__ — it does not make any HTTP calls.

    adapter_http = client.session.get_adapter("http://test.com")
    adapter_https = client.session.get_adapter("https://test.com")

    assert isinstance(adapter_http, HTTPAdapter)
    assert isinstance(adapter_https, HTTPAdapter)

    retry_strategy = adapter_http.max_retries

    assert isinstance(retry_strategy, Retry)
    assert retry_strategy.total == 5
    assert retry_strategy.backoff_factor == 1
    assert set(retry_strategy.status_forcelist) == {500, 502, 503, 504}
    assert retry_strategy.allowed_methods == ["GET"]


def test_client_exhausted_retries_raises_error(historical_airpollution_url, client, mock_requests):
    # Integration test: confirms that 5xx responses are retried and ultimately bubble up as HTTPError.
    # Covers the full retry cycle — no need to repeat this for every method since retry is session-level.

    mock_requests.get(historical_airpollution_url, status_code=500)

    with pytest.raises(requests.exceptions.HTTPError) as excinfo:
        client.get_historical_airpollution_data(
            city="TestCity", lat=10.5, lon=20.5, start_ts=10000, end_ts=20000
        )

    assert excinfo.value.response.status_code == 500


def test_network_error_raises_exception(historical_airpollution_url, mock_requests, client):
    # Verifies that low-level network failures (e.g. DNS, TCP reset) are not swallowed by the client.

    mock_requests.get(historical_airpollution_url, exc=requests.ConnectionError("Network failed"))

    with pytest.raises(requests.ConnectionError):
        client.get_historical_airpollution_data(
            city="TestCity", lat=10.5, lon=20.5, start_ts=10000, end_ts=20000
        )


def test_context_manager_closes_session(base_url, api_key):
    # Ensures the session is always closed on __exit__, even when no exception occurred.
    # Uses a MagicMock so we can assert close() was called without a real HTTP session.
    from unittest.mock import MagicMock

    client = OpenWeatherApiClient(base_url, api_key)
    client.session = MagicMock()

    with client:
        pass

    client.session.close.assert_called_once()


def test_timestamp_conversion_to_int(base_url, api_key, mock_requests, historical_airpollution_url):
    # Verifies that float timestamps are truncated to int before being sent as query params.
    # The API rejects non-integer Unix timestamps, so this conversion must happen in the client.
    mock_response: dict[str, Any] = {"list": []}
    mock_requests.get(historical_airpollution_url, json=mock_response, status_code=200)

    client = OpenWeatherApiClient(base_url, api_key)

    result = client.get_historical_airpollution_data(
        city="TestCity", lat=10.5, lon=20.5, start_ts=10000.7, end_ts=20000.9
    )

    assert result == mock_response

    # Verify timestamps were converted to integers in request
    query_string = mock_requests.last_request.qs
    assert query_string["start"] == ["10000"]
    assert query_string["end"] == ["20000"]

    client.session.close()


def test_timeout_exception_raised(client, mock_requests, historical_airpollution_url):
    # Confirms that request timeouts are propagated to the caller rather than silently swallowed.
    mock_requests.get(historical_airpollution_url, exc=requests.Timeout("Request timeout"))

    with pytest.raises(requests.Timeout):
        client.get_historical_airpollution_data(
            city="TestCity", lat=10.5, lon=20.5, start_ts=10000, end_ts=20000
        )


def test_base_url_trailing_slash_removed(api_key):
    # Trailing slashes on base_url would break urljoin path construction, so the client strips them.
    base_url_with_slash = "http://api.test.com/data/"

    client = OpenWeatherApiClient(base_url_with_slash, api_key)

    assert client.base_url == "http://api.test.com/data"

    client.session.close()


def test_multiple_consecutive_requests(mock_requests, client, historical_airpollution_url):
    # Verifies that the shared session handles sequential requests independently,
    # returning a different response each time (simulates real pagination/batching scenarios).
    mock_response_1 = {"list": [{"dt": 1}]}
    mock_response_2 = {"list": [{"dt": 2}]}

    mock_requests.get(
        historical_airpollution_url,
        [{"json": mock_response_1, "status_code": 200}, {"json": mock_response_2, "status_code": 200}],
    )

    result1 = client.get_historical_airpollution_data(
        city="City1", lat=10.5, lon=20.5, start_ts=10000, end_ts=20000
    )

    result2 = client.get_historical_airpollution_data(
        city="City2", lat=30.5, lon=40.5, start_ts=30000, end_ts=40000
    )

    assert result1 == mock_response_1
    assert result2 == mock_response_2
    assert mock_requests.call_count == 2


def test_get_historical_weather_data_single_page_filters_and_cleans_meta(
    client, mock_requests, historical_weather_url
):
    # Ensures one weather page is yielded, records beyond end_ts are filtered,
    # and pagination metadata keys are removed from yielded payloads.
    mock_requests.get(
        historical_weather_url,
        json={
            "lat": 10.0,
            "lon": 20.0,
            "data": [
                {"dt": 1000, "temp": 21.1},
                {"dt": 4600, "temp": 20.0},
                {"dt": 8200, "temp": 19.5},
            ],
            "next": "token-next",
            "prev": "token-prev",
        },
        status_code=200,
    )

    pages = list(
        client.get_historical_weather_data(city="TestCity", lat=10.0, lon=20.0, start_ts=1000, end_ts=5000)
    )

    assert len(pages) == 1
    assert pages[0]["data"] == [{"dt": 1000, "temp": 21.1}, {"dt": 4600, "temp": 20.0}]
    assert "next" not in pages[0]
    assert "prev" not in pages[0]


def test_get_historical_weather_data_paginates_forward(client, mock_requests, historical_weather_url):
    # Ensures the method advances using (last dt + 3600), making multiple requests
    # when the requested range spans more than one API page.
    mock_requests.get(
        historical_weather_url,
        [
            {
                "json": {
                    "data": [
                        {"dt": 1000, "temp": 11.0},
                        {"dt": 4600, "temp": 12.0},
                    ]
                },
                "status_code": 200,
            },
            {
                "json": {
                    "data": [
                        {"dt": 8200, "temp": 13.0},
                        {"dt": 11800, "temp": 14.0},
                    ]
                },
                "status_code": 200,
            },
        ],
    )

    pages = list(
        client.get_historical_weather_data(city="TestCity", lat=10.0, lon=20.0, start_ts=1000, end_ts=9000)
    )

    assert len(pages) == 2
    assert mock_requests.call_count == 2

    first_call_qs = mock_requests.request_history[0].qs
    second_call_qs = mock_requests.request_history[1].qs

    assert first_call_qs["start"] == ["1000"]
    assert second_call_qs["start"] == ["8200"]


def test_get_historical_weather_data_stops_on_empty_page(client, mock_requests, historical_weather_url):
    # If API returns no data for a page, the generator should stop cleanly
    # and not yield empty payloads.
    mock_requests.get(historical_weather_url, json={"data": []}, status_code=200)

    pages = list(
        client.get_historical_weather_data(city="TestCity", lat=10.0, lon=20.0, start_ts=1000, end_ts=9000)
    )

    assert pages == []
    assert mock_requests.call_count == 1


def test_get_historical_weather_data_http_error_propagates(client, mock_requests, historical_weather_url):
    # HTTP failures should be raised to caller so orchestration can retry/fail visibly.
    mock_requests.get(historical_weather_url, status_code=500)

    with pytest.raises(requests.HTTPError) as excinfo:
        list(
            client.get_historical_weather_data(
                city="TestCity", lat=10.0, lon=20.0, start_ts=1000, end_ts=9000
            )
        )

    assert excinfo.value.response is not None
    assert excinfo.value.response.status_code == 500
