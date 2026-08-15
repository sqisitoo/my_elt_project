from unittest.mock import patch

import pytest

from plugins.common.clients.snowflake_client import SnowflakeClient

SNOWFLAKE_CONN_ID = "snowflake_conn"
TARGET_SCHEMA = "RAW.AIR_POLLUTION"
TARGET_TABLE = "RAW_AIR_POLLUTION"
S3_STAGE = "s3_stage"
S3_PREFIX = "bronze/air_pollution/date=2026-06-25"


@pytest.fixture
def mock_hook():
    """Fixture providing a mocked SnowflakeHook instance."""
    with patch("plugins.common.clients.snowflake_client.SnowflakeHook") as mock_cls:
        yield mock_cls.return_value


@pytest.fixture
def client():
    """Fixture providing a SnowflakeClient with the test connection ID."""
    return SnowflakeClient(snowflake_conn_id=SNOWFLAKE_CONN_ID)


def test_load_json_calls_hook_with_correct_conn_id(client, mock_hook):
    """SnowflakeHook must be initialised with the connection ID passed to the client."""
    with patch("plugins.common.clients.snowflake_client.SnowflakeHook") as mock_cls:
        mock_cls.return_value = mock_hook
        client.load_json_to_snowflake(
            s3_stage=S3_STAGE,
            target_schema=TARGET_SCHEMA,
            target_table=TARGET_TABLE,
            s3_prefix=S3_PREFIX,
        )
        mock_cls.assert_called_once_with(snowflake_conn_id=SNOWFLAKE_CONN_ID)


def test_load_json_executes_sql(client, mock_hook):
    """hook.run() must be called exactly once with the generated SQL string."""
    client.load_json_to_snowflake(
        s3_stage=S3_STAGE,
        target_schema=TARGET_SCHEMA,
        target_table=TARGET_TABLE,
        s3_prefix=S3_PREFIX,
    )

    mock_hook.run.assert_called_once()
    sql = mock_hook.run.call_args.args[0]
    assert isinstance(sql, str)


def test_load_json_sql_targets_correct_table(client, mock_hook):
    """Generated SQL must reference the exact schema and table provided."""
    client.load_json_to_snowflake(
        s3_stage=S3_STAGE,
        target_schema=TARGET_SCHEMA,
        target_table=TARGET_TABLE,
        s3_prefix=S3_PREFIX,
    )

    sql = mock_hook.run.call_args.args[0]
    assert f"COPY INTO {TARGET_SCHEMA}.{TARGET_TABLE}" in sql


def test_load_json_sql_scopes_to_partition_prefix(client, mock_hook):
    """The FROM clause must address the partition prefix (ADR-0004), not an explicit file list."""
    client.load_json_to_snowflake(
        s3_stage=S3_STAGE,
        target_schema=TARGET_SCHEMA,
        target_table=TARGET_TABLE,
        s3_prefix=S3_PREFIX,
    )

    sql = mock_hook.run.call_args.args[0]
    assert f'"{S3_STAGE}"/{S3_PREFIX}' in sql
    assert "FILES = (" not in sql


def test_load_json_sql_is_idempotent(client, mock_hook):
    """FORCE = FALSE must be present to prevent re-loading already-ingested files."""
    client.load_json_to_snowflake(
        s3_stage=S3_STAGE,
        target_schema=TARGET_SCHEMA,
        target_table=TARGET_TABLE,
        s3_prefix=S3_PREFIX,
    )

    sql = mock_hook.run.call_args.args[0]
    assert "FORCE = FALSE" in sql


def test_load_json_sql_allows_uncertain_files(client, mock_hook):
    """
    LOAD_UNCERTAIN_FILES = TRUE must be present
    so objects with expired load metadata are retried (ADR-0004).
    """
    client.load_json_to_snowflake(
        s3_stage=S3_STAGE,
        target_schema=TARGET_SCHEMA,
        target_table=TARGET_TABLE,
        s3_prefix=S3_PREFIX,
    )

    sql = mock_hook.run.call_args.args[0]
    assert "LOAD_UNCERTAIN_FILES = TRUE" in sql


def test_load_json_sql_references_stage(client, mock_hook):
    """The FROM clause must reference the correct S3 stage name."""
    client.load_json_to_snowflake(
        s3_stage=S3_STAGE,
        target_schema=TARGET_SCHEMA,
        target_table=TARGET_TABLE,
        s3_prefix=S3_PREFIX,
    )

    sql = mock_hook.run.call_args.args[0]
    assert f'"{S3_STAGE}"' in sql
