import logging
from typing import Any, cast

import requests
from pydantic import SecretStr
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

ENDPOINTS = {"historical_airpollution_data": "/data/2.5/air_pollution/history"}

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
