import pytest
from airflow.models import DagBag

DAGS_FOLDER = "dags"
DAG_ID = "weather_snowflake_dag"


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

    assert get_cities_config in extract_data.upstream_list
    assert extract_data in load_to_snowflake.upstream_list
