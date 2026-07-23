import pytest

from plugins.common.utils.dbt import build_dbt_command


@pytest.mark.parametrize("subcommand", ["build", "source freshness", "test", "run"])
def test_build_dbt_command_contains_required_env_vars(subcommand):
    cmd = build_dbt_command(subcommand)

    assert "$DBT_VENV_PATH" in cmd
    assert "$DBT_PROJECT_DIR" in cmd
    assert "$DBT_PROFILES_DIR" in cmd
    assert "$DBT_TARGET" in cmd


def test_build_dbt_command_includes_subcommand():
    assert "build" in build_dbt_command("build")
    assert "source freshness" in build_dbt_command("source freshness")


def test_build_dbt_command_includes_select():
    assert "--select model_name" in build_dbt_command("build", "model_name")
