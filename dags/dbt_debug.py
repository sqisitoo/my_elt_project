from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import dag

from plugins.common.config import settings


@dag(dag_id="__test_dbt_integration", schedule=None, catchup=False, tags=["debug"])
def test_dbt_integration_dag():

    BashOperator(task_id="dbt_debug", bash_command=f"{settings.dbt.bin_path} debug")


test_dbt_integration_dag()
