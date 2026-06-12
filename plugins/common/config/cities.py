import csv
from pathlib import Path

from pydantic import BaseModel


class City(BaseModel):
    """
    Represents a geographic location with coordinates.

    Attributes:
        name (str): The name of the city.
        lat (float): Latitude coordinate of the city.
        lon (float): Longitude coordinate of the city.
    """

    name: str
    lat: float
    lon: float


def get_cities_config(config_path: Path | None = None) -> list[City]:
    """
    Load and parse city coordinates from a CSV configuration file.

    The CSV file must contain the columns: ``name``, ``lat``, and ``lon``.
    Each row is converted to a ``City`` model. If no path is provided,
    the function reads ``cities_config.csv`` from this module directory.

    Args:
        config_path (Path | None): Path to the CSV configuration file.

    Returns:
        list[City]: Parsed and validated list of cities.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        KeyError: If one of the required CSV columns is missing.
        ValueError: If latitude or longitude cannot be converted to float.
    """
    # Use default config path if none provided
    if config_path is None:
        project_root = Path(__file__).resolve().parents[3]
        config_path = project_root / "dbt_project" / "seeds" / "cities_config.csv"

    with open(config_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            City(
                name=row["name"],
                lat=float(row["lat"]),
                lon=float(row["lon"]),
            )
            for row in reader
        ]
