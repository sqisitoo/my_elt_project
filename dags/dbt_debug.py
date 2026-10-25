from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag

from plugins.common.utils.dbt import build_dbt_command


@dag(dag_id="__test_dbt_integration", schedule=None, catchup=False, tags=["debug"])
def test_dbt_integration_dag():

    BashOperator(task_id="dbt_debug", bash_command=build_dbt_command("debug"))


test_dbt_integration_dag()
