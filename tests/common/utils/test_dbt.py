import pytest

from plugins.common.config import settings
from plugins.common.utils.dbt import build_dbt_command


@pytest.mark.parametrize("subcommand", ["build", "source freshness", "test", "run"])
def test_build_dbt_command_uses_configured_dbt(subcommand):
    cmd = build_dbt_command(subcommand)

    assert cmd.startswith(f"{settings.dbt.bin_path} {subcommand} ")
    assert f"--project-dir {settings.dbt.project_dir}" in cmd
    assert f"--profiles-dir {settings.dbt.profiles_dir}" in cmd
    assert f"--target {settings.dbt.target}" in cmd


def test_build_dbt_command_includes_subcommand():
    assert "build" in build_dbt_command("build")
    assert "source freshness" in build_dbt_command("source freshness")


def test_build_dbt_command_includes_select():
    assert "--select model_name" in build_dbt_command("build", "model_name")
