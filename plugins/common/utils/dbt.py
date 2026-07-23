def build_dbt_command(subcommand: str, select: str = "") -> str:
    return (
        f"$DBT_VENV_PATH/bin/dbt {subcommand} "
        f"--project-dir $DBT_PROJECT_DIR "
        f"--profiles-dir $DBT_PROFILES_DIR "
        f"--target $DBT_TARGET "
        f"{f'--select {select}' if select else ''}"
    )
