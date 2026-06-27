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
        file_names: list[str],
    ) -> None:
        """Copy JSON files from an S3 stage into a Snowflake raw table.

        Executes a ``COPY INTO`` statement scoped to the provided file list.
        Idempotency is guaranteed by ``FORCE = FALSE``: files already present
        in Snowflake's load history for this table are silently skipped.

        Args:
            s3_stage (str): Name of the Snowflake external stage.
            target_schema (str): Fully qualified Snowflake schema
                (e.g. ``RAW.AIR_POLLUTION``).
            target_table (str): Target table name within the schema.
            file_names (list[str]): S3 keys to load, relative to the stage root.
                Only these files are included in the ``FILES`` clause.
        """
        # Snowflake's FILES clause requires a comma-separated list of quoted strings.
        files_list = ", ".join(f"'{file}'" for file in file_names)

        sql = f"""
            COPY INTO {target_schema}.{target_table} (RAW_PAYLOAD, _SOURCE_FILE)
            FROM (
                SELECT $1, METADATA$FILENAME
                FROM @{target_schema}."{s3_stage}"
            )
            FILES = ({files_list})
            FILE_FORMAT = (TYPE = 'JSON')
            ON_ERROR = 'ABORT_STATEMENT'
            FORCE = FALSE
        """

        hook = SnowflakeHook(snowflake_conn_id=self._snowflake_conn_id)
        hook.run(sql)
        logger.info(f"COPY INTO {target_schema}.{target_table} completed")