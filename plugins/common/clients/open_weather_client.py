import logging
from collections.abc import Iterator
from typing import Any, cast
from urllib.parse import urljoin

import requests
from pydantic import SecretStr
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

ENDPOINTS = {
    "historical_airpollution_data": "/data/2.5/air_pollution/history",
    "historical_weather_data": "/data/4.0/onecall/timeline/1h",
}


class OpenWeatherApiClient:
    """
    HTTP client for the OpenWeatherMap API.

    Features:
    - Automatic retry logic for resilient API calls (5xx errors)
    - Secure API key management using Pydantic SecretStr
    - Session pooling for efficient connection reuse
    - Context manager support for proper resource cleanup
    """

    def __init__(self, base_url: str, api_key: SecretStr):
        """
        Initialize the OpenWeatherMap API client.

        Args:
            base_url: Base URL ('https://api.openweathermap.org')
            api_key: OpenWeather API key wrapped in SecretStr for secure handling
        """
        # Store base URL without trailing slash for consistent path construction
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

        # Create a persistent session for connection pooling
        self.session = requests.Session()

        # Configure retry strategy: retry up to 5 times on server errors (5xx)
        # Use exponential backoff (1s, 2s, 4s, 8s, 16s) between retries
        # Only retry GET requests to avoid unintended side effects
        retries = Retry(
            total=5,
            backoff_factor=1,
            allowed_methods=["GET"],
            status_forcelist=[500, 502, 503, 504],  # Retry on server errors only
        )

        # Mount retry adapter to both HTTP and HTTPS
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter=adapter)
        self.session.mount("https://", adapter=adapter)

        # Set default query parameter (API key) for all requests
        self.session.params = {"appid": api_key.get_secret_value()}

        logger.info("OpenWeatherApiClient initialized with session pooling enabled")

    def get_historical_airpollution_data(
        self, city: str, lat: float, lon: float, start_ts: int | float, end_ts: int | float
    ) -> dict[str, Any]:
        """
        Retrieve historical air pollution data for a specific location and time range.

        Args:
            city: City name (for logging context only, not sent to API)
            lat: Latitude coordinate
            lon: Longitude coordinate
            start_ts: Unix timestamp (seconds) marking the start of the time range
            end_ts: Unix timestamp (seconds) marking the end of the time range

        Returns:
            Dictionary containing the parsed JSON response from OpenWeatherMap API

        Raises:
            requests.HTTPError: If the API returns an error status code (after retries)
            requests.RequestException: For network-related errors
        """
        # Build query parameters for the API request
        params = {"lat": lat, "lon": lon, "start": int(start_ts), "end": int(end_ts)}
        endpoint = ENDPOINTS["historical_airpollution_data"]
        full_url = urljoin(self.base_url, endpoint)

        try:
            logger.info(
                f"Fetching air pollution data for {city} "
                f"(lat={lat}, lon={lon}), time range={start_ts}-{end_ts}"
            )

            # Make GET request to the configured endpoint
            # Session automatically includes API key in params
            # Timeout prevents hanging connections
            response = self.session.get(full_url, params=params, timeout=10)
            response.raise_for_status()  # Raise exception for non-2xx status codes

            return cast(dict[str, Any], response.json())

        except requests.HTTPError as e:
            logger.error(f"HTTP error from OpenWeatherMap API: {e.response.status_code} - {e}")
            raise
        except requests.RequestException as e:
            logger.error(f"Network error while fetching air pollution data: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise

    def get_historical_weather_data(
        self, city: str, lat: float, lon: float, start_ts: int | float, end_ts: int | float
    ) -> Iterator[dict[str, Any]]:
        """
        Retrieve historical hourly weather data for a location over a time range.

        The OpenWeather timeline endpoint returns results in chunks, so this method
        paginates forward from ``start_ts`` until the requested range is exhausted.
        Each yielded payload contains only records whose timestamps are within the
        requested end bound.

        Args:
            city: City name used only for logging context.
            lat: Latitude coordinate.
            lon: Longitude coordinate.
            start_ts: Inclusive Unix timestamp marking the start of the range.
            end_ts: Inclusive Unix timestamp marking the end of the range.

        Yields:
            Parsed API response dictionaries for each page of historical hourly weather data.

        Raises:
            RuntimeError: If pagination exceeds the configured safety page limit.
            requests.HTTPError: If the API returns an error status code.
            requests.RequestException: For network-related errors.
        """
        endpoint = ENDPOINTS["historical_weather_data"]
        full_url = urljoin(self.base_url, endpoint)

        current_ts = start_ts

        max_pages = 500
        page = 0
        logger.info(
            "Fetching historical weather data for %s (lat=%s, lon=%s), time range=%s-%s",
            city,
            lat,
            lon,
            start_ts,
            end_ts,
        )

        while current_ts < end_ts:
            if page >= max_pages:
                raise RuntimeError(f"Exceeded max pages limit ({max_pages}), possible infinite loop")

            try:
                logger.debug(
                    "Requesting historical weather page %s for %s starting at %s",
                    page + 1,
                    city,
                    current_ts,
                )

                params: dict[str, float | int | str] = {
                    "lat": lat,
                    "lon": lon,
                    "start": int(current_ts),
                    "units": "metric",
                }

                response = self.session.get(full_url, params=params, timeout=10)
                response.raise_for_status()
                data = cast(dict[str, Any], response.json())

            except requests.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else "unknown"
                logger.error(
                    "HTTP error while fetching historical weather data for %s: %s - %s",
                    city,
                    status_code,
                    e,
                )
                raise
            except requests.RequestException as e:
                logger.error(
                    "Network error while fetching historical weather data for %s: %s",
                    city,
                    e,
                )
                raise
            except Exception as e:
                logger.error("Unexpected error while fetching historical weather data for %s: %s", city, e)
                raise

            hourly = data.get("data", [])
            if not hourly:
                logger.warning(
                    "Historical weather response for %s was empty at start_ts=%s; stopping pagination",
                    city,
                    current_ts,
                )
                break

            hourly_in_range = [record for record in hourly if record["dt"] < end_ts]

            data["data"] = hourly_in_range
            data.pop("next", None)
            data.pop("prev", None)

            last_record_ts = hourly[-1]["dt"]
            logger.info(
                "Fetched historical weather page %s for %s with %s in-range records; next start_ts=%s",
                page + 1,
                city,
                len(hourly_in_range),
                last_record_ts + 3600,
            )

            current_ts = last_record_ts + 3600

            page += 1
            yield data

    def __enter__(self):
        """Support using the client as a context manager."""
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        """
        Clean up resources when exiting the context manager.

        Args:
            exc_type: Exception type if an error occurred, None otherwise
            exc_value: Exception instance if an error occurred, None otherwise
            exc_tb: Traceback object if an error occurred, None otherwise
        """
        # Log any exceptions that occurred within the context
        if exc_type:
            logger.error(f"Context exited with error: {exc_type.__name__}: {exc_value}")

        # Close the session to release connection pool resources
        self.session.close()
        logger.info("Session closed and resources cleaned up")
