import pytest
from airflow.models import DagBag

DAGS_FOLDER = "dags"
DAG_ID = "weather_snowflake_dag"
# Airflow-to-dbt orchestration contract for the weather pipeline.
FRESHNESS_SELECTOR = "source:openweather_weather"
BUILD_SELECTOR = "+stg_openweather__weather"


@pytest.fixture(scope="module")
def dag_bag():
    """Load DAGs once per module; module scope avoids repeated filesystem parsing."""
    return DagBag(dag_folder=DAGS_FOLDER)


@pytest.fixture(scope="module")
def weather_dag(dag_bag):
    """Retrieve the target DAG from the loaded DagBag."""
    return dag_bag.dags.get(DAG_ID)


def test_weather_dag_exists(weather_dag):
    """Fail fast with a clear signal if the DAG was not registered in DagBag."""
    assert weather_dag is not None


def test_weather_dag_loadings_no_import_errors(dag_bag):
    """DagBag should import every DAG module in the folder without import-time errors."""
    assert len(dag_bag.import_errors) == 0


def test_weather_dag_structure_and_settings(weather_dag):
    """Validate the top-level DAG settings defined in the @dag decorator."""
    assert weather_dag.schedule == "@daily"
    assert weather_dag.catchup is False
    assert weather_dag.default_args.get("retries") == 2


def test_weather_dag_tasks_exist(weather_dag):
    """Keep the expected task set explicit so accidental task graph changes are visible."""
    tasks = weather_dag.task_ids
    expected_tasks = {
        "get_cities_config",
        "extract_data",
        "load_to_snowflake",
        "run_dbt_source_freshness",
        "run_dbt_build",
    }

    assert set(tasks) == expected_tasks


def test_weather_dag_dependencies(weather_dag):
    """
    Verify the intended execution order:
    get_cities_config >> extract_data >> load_to_snowflake
    """
    get_cities_config = weather_dag.get_task("get_cities_config")
    extract_data = weather_dag.get_task("extract_data")
    load_to_snowflake = weather_dag.get_task("load_to_snowflake")
    run_dbt_source_freshness = weather_dag.get_task("run_dbt_source_freshness")
    run_dbt_build = weather_dag.get_task("run_dbt_build")

    assert get_cities_config in extract_data.upstream_list
    assert extract_data in load_to_snowflake.upstream_list
    assert load_to_snowflake in run_dbt_source_freshness.upstream_list
    assert run_dbt_source_freshness in run_dbt_build.upstream_list


def test_dbt_tasks_bash_commands_use_env_vars(weather_dag):
    for task_id in ("run_dbt_source_freshness", "run_dbt_build"):
        cmd = weather_dag.get_task(task_id).bash_command
        assert "$DBT_VENV_PATH" in cmd
        assert "$DBT_TARGET" in cmd
        assert "$DBT_PROJECT_DIR" in cmd
        assert "$DBT_PROFILES_DIR" in cmd


def test_dbt_source_freshness_task_use_proper_selector(weather_dag):
    cmd = weather_dag.get_task("run_dbt_source_freshness").bash_command
    assert f"--select {FRESHNESS_SELECTOR}" in cmd


def test_dbt_source_build_task_use_proper_selector(weather_dag):
    cmd = weather_dag.get_task("run_dbt_build").bash_command
    assert f"--select {BUILD_SELECTOR}" in cmd
