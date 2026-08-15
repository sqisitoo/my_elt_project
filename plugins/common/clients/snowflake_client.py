import logging

from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook

logger = logging.getLogger(__name__)


class SnowflakeClient:
    """Thin wrapper over ``SnowflakeHook`` for raw-layer data loading.

    Encapsulates the Snowflake connection ID and exposes load operations
    used by pipeline tasks to ingest staged S3 files into raw tables.
    """

    def __init__(self, snowflake_conn_id: str) -> None:
        self._snowflake_conn_id = snowflake_conn_id

    def load_json_to_snowflake(
        self,
        *,
        s3_stage: str,
        target_schema: str,
        target_table: str,
        s3_prefix: str,
    ) -> None:
        """Copy JSON files under an S3 stage prefix into a Snowflake raw table.

        Executes a ``COPY INTO`` scoped to the partition prefix (ADR-0004),
        not to an explicit file list: it loads whatever is new under that
        prefix, regardless of which run wrote it. ``FORCE = FALSE`` skips
        objects already in this table's load history; ``LOAD_UNCERTAIN_FILES
        = TRUE`` still attempts objects whose load metadata has expired
        (Snowflake keeps it for 64 days), so re-running a date is how
        stranded objects get picked up.

        Args:
            s3_stage (str): Name of the Snowflake external stage.
            target_schema (str): Fully qualified Snowflake schema
                (e.g. ``RAW.AIR_POLLUTION``).
            target_table (str): Target table name within the schema.
            s3_prefix (str): Partition prefix to load, relative to the stage root
                (e.g. ``bronze/air_pollution/date=2026-06-27``). All objects under it are considered.
        """

        sql = f"""
            COPY INTO {target_schema}.{target_table} (RAW_PAYLOAD, _SOURCE_FILE)
            FROM (
                SELECT $1, METADATA$FILENAME
                FROM @{target_schema}."{s3_stage}"/{s3_prefix}
            )
            FILE_FORMAT = (TYPE = 'JSON')
            ON_ERROR = 'ABORT_STATEMENT'
            FORCE = FALSE
            LOAD_UNCERTAIN_FILES = TRUE
        """

        hook = SnowflakeHook(snowflake_conn_id=self._snowflake_conn_id)
        hook.run(sql)
        logger.info(f"COPY INTO {target_schema}.{target_table} completed")
