from plugins.common.config import settings


def build_dbt_command(subcommand: str, select: str = "") -> str:
    # Values are rendered into the command at DAG parse time, not expanded by bash at
    # task run time.
    dbt = settings.dbt
    return (
        f"{dbt.bin_path} {subcommand} "
        f"--project-dir {dbt.project_dir} "
        f"--profiles-dir {dbt.profiles_dir} "
        f"--target {dbt.target} "
        f"{f'--select {select}' if select else ''}"
    )
