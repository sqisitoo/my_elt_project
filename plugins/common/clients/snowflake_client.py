import logging

from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook

logger = logging.getLogger(__name__)


class SnowflakeClient:

    def __init__(self, snowflake_conn_id: str) -> None:
        self._snowflake_conn_id = snowflake_conn_id
    
    def load_json_to_snowflake(
        *,
        s3_stage: str,
        target_schema: str,
        target_table: str,
        file_names: list[str]
    ) -> None:
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