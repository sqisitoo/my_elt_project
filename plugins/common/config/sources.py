import yaml

from pydantic import BaseModel
from pathlib import Path


class DataSource(BaseModel):
    """
    Represents a raw-layer load target and its associated S3 stage.

    Attributes:
        target_schema (str): Fully qualified Snowflake schema (e.g. ``RAW.AIR_POLLUTION``).
        target_table (str): Snowflake table name within the target schema.
        s3_stage (str): Name of the Snowflake external stage pointing to the S3 bucket.
    """

    target_schema: str
    target_table: str
    s3_stage: str


def get_source_config(name: str, config_path: Path | None = None) -> DataSource:
    """
    Look up a data source entry by name from the central sources registry.

    Reads ``sources.yml`` from this module's directory by default and returns
    a validated ``DataSource`` model for the requested source. The ``name``
    argument must exactly match a key under the ``sources:`` mapping in the
    YAML file.

    Args:
        name (str): Source identifier as defined in ``sources.yml``
            (e.g. ``"air_pollution"``). Used as a lookup key.
        config_path (Path | None): Path to the YAML registry file. Defaults
            to ``sources.yml`` located in the same directory as this module.

    Returns:
        DataSource: Validated load configuration for the requested source.

    Raises:
        KeyError: If ``name`` does not exist in the sources registry.
        FileNotFoundError: If the configuration file cannot be found.
    """
    # Use default config path if none provided
    if config_path is None:
        config_path = Path(__file__).parent / "sources.yml"

    with open(config_path) as f:
        sources_metadata = yaml.safe_load(f)
    
    data_source = sources_metadata["sources"][name]
    
    return DataSource(**data_source)
    