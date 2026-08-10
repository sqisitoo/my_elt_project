import pytest
from airflow.models import DagBag

DAGS_FOLDER = "dags"
DAG_ID = "air_pollution_snowflake_dag"
# Airflow-to-dbt orchestration contract for the air_pollution pipeline.
FRESHNESS_SELECTOR = "source:openweather_air_pollution"
BUILD_SELECTOR = "+fct_air_quality"


@pytest.fixture(scope="module")
def dag_bag():
    """Load DAGs once per module; module scope avoids repeated filesystem parsing."""
    return DagBag(dag_folder=DAGS_FOLDER)


@pytest.fixture(scope="module")
def air_pollution_dag(dag_bag):
    """Retrieve the target DAG from the loaded DagBag."""
    dag = dag_bag.dags.get(DAG_ID)

    return dag


def test_air_pollution_dag_exists(air_pollution_dag):
    """Fail fast with a clear signal if the DAG was not registered in DagBag."""
    assert air_pollution_dag is not None


def test_air_pollution_dag_loadings_no_import_errors(dag_bag):
    """DagBag should import every DAG module in the folder without import-time errors."""
    assert len(dag_bag.import_errors) == 0


def test_air_pollution_dag_structure_and_settings(air_pollution_dag):
    """Validate the top-level DAG settings defined in the @dag decorator."""
    assert air_pollution_dag.schedule == "@daily"
    assert air_pollution_dag.catchup is False
    assert air_pollution_dag.default_args.get("retries") == 2


def test_air_pollution_dag_tasks_exist(air_pollution_dag):
    """Keep the expected task set explicit so accidental task graph changes are visible."""
    tasks = air_pollution_dag.task_ids
    expected_tasks = {
        "get_cities_config",
        "extract_data",
        "load_to_snowflake",
        "run_dbt_source_freshness",
        "run_dbt_build",
    }

    assert set(tasks) == expected_tasks


def test_air_pollution_dag_dependencies(air_pollution_dag):
    """
    Verify the intended execution order:
    get_cities_config >> extract_data >> load_air_pollution_data >> run_dbt_source_freshness >> run_dbt
    """
    get_cities_config = air_pollution_dag.get_task("get_cities_config")
    extract_data = air_pollution_dag.get_task("extract_data")
    load_to_snowflake = air_pollution_dag.get_task("load_to_snowflake")
    run_dbt_source_freshness = air_pollution_dag.get_task("run_dbt_source_freshness")
    run_dbt_build = air_pollution_dag.get_task("run_dbt_build")

    assert get_cities_config in extract_data.upstream_list
    assert extract_data in load_to_snowflake.upstream_list
    assert load_to_snowflake in run_dbt_source_freshness.upstream_list
    assert run_dbt_source_freshness in run_dbt_build.upstream_list


def test_load_to_snowflake_tolerates_skipped_cities(air_pollution_dag):
    """A city extract skipped for empty API data (#43) must not skip the load for the rest (ADR-0004)."""
    from airflow.task.trigger_rule import TriggerRule

    load_to_snowflake = air_pollution_dag.get_task("load_to_snowflake")
    assert load_to_snowflake.trigger_rule == TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS


def test_dbt_tasks_bash_commands_use_env_vars(air_pollution_dag):
    for task_id in ("run_dbt_source_freshness", "run_dbt_build"):
        cmd = air_pollution_dag.get_task(task_id).bash_command
        assert "$DBT_VENV_PATH" in cmd
        assert "$DBT_TARGET" in cmd
        assert "$DBT_PROJECT_DIR" in cmd
        assert "$DBT_PROFILES_DIR" in cmd


def test_dbt_source_freshness_task_use_proper_selector(air_pollution_dag):
    cmd = air_pollution_dag.get_task("run_dbt_source_freshness").bash_command
    assert f"--select {FRESHNESS_SELECTOR}" in cmd


def test_dbt_source_build_task_use_proper_selector(air_pollution_dag):
    cmd = air_pollution_dag.get_task("run_dbt_build").bash_command
    assert f"--select {BUILD_SELECTOR}" in cmd
