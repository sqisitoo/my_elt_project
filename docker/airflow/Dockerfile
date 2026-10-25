FROM apache/airflow:slim-3.1.6-python3.10

ARG PYTHON_VERSION=3.10
ARG CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
# dbt lives in its own venv, isolated from Airflow's dependencies.
# _DBTSettings.venv_path (plugins/common/config/settings.py) reads this ENV and
# carries the same path as its default: change both together. Do not duplicate
# it in .env: compose's env_file would override this value.
ENV DBT_VENV_PATH="/opt/airflow/dbt_venv"

ADD --chown=airflow:airflow ${CONSTRAINT_URL} /constraints.txt
COPY --chown=airflow:airflow docker/airflow/requirements.txt /requirements.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /requirements.txt --constraint /constraints.txt

RUN python -m venv ${DBT_VENV_PATH} && \
    ${DBT_VENV_PATH}/bin/pip install --no-cache-dir dbt-snowflake

COPY --chown=airflow:airflow dbt_project /opt/airflow/dbt_project

RUN ${DBT_VENV_PATH}/bin/dbt deps \
    --project-dir /opt/airflow/dbt_project

COPY --chown=airflow:airflow dags /opt/airflow/dags
COPY --chown=airflow:airflow plugins /opt/airflow/plugins
