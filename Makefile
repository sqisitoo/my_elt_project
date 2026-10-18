# .ONESHELL runs each recipe as ONE bash script, so the exit code is that of the LAST
# command: without `set -eo pipefail` an earlier failure is swallowed and the target goes
# green. Every multi-line target below must start with it.
.ONESHELL:
.PHONY: lint lint_tf lint_dbt test build check install_deps
SHELL:= /bin/bash

AIRFLOW_VERSION ?= 3.1.6
PYTHON_VERSION ?= 3.10
DBT_VENV ?= dbt_venv
DBT_BIN := $(DBT_VENV)/bin/dbt
DBT_PIP := $(DBT_VENV)/bin/pip

lint:
	@set -eo pipefail
	ruff check .
	ruff format . --check
	mypy .

test:
	pytest

# Do not add -lockfile=readonly to init: .terraform.lock.hcl carries h1: hashes for one
# platform only (windows_amd64), and a Linux runner has to append its own. Fix first with
# `terraform providers lock -platform=windows_amd64 -platform=linux_amd64`.
lint_tf:
	@set -eo pipefail
	terraform -chdir=terraform fmt -check -recursive
	terraform -chdir=terraform init -backend=false -input=false
	terraform -chdir=terraform validate

$(DBT_BIN):
	@set -eo pipefail
	python3 -m venv $(DBT_VENV)
	$(DBT_PIP) install --upgrade pip
	$(DBT_PIP) install dbt-snowflake

lint_dbt: $(DBT_BIN)
	@set -eo pipefail
	$(DBT_BIN) deps --project-dir dbt_project --profiles-dir dbt_project --target ci
	$(DBT_BIN) parse --project-dir dbt_project --profiles-dir dbt_project --target ci


# Local development entrypoint inside the dev container.
# lint_tf stays separate because the dev container does not have Terraform access;
check: lint lint_dbt test 

build:
	docker build -f docker/airflow/Dockerfile -t my-pet-project:latest .

install_deps:
	@set -euo pipefail
	@python -m pip install --upgrade pip
	@CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-$(AIRFLOW_VERSION)/constraints-$(PYTHON_VERSION).txt"
	@echo "Installing with constraints from: $$CONSTRAINT_URL"

	@TMP_CONSTRAINTS=$$(mktemp)
	@trap 'rm -f "$$TMP_CONSTRAINTS"' EXIT

	@if ! curl -fsSL "$$CONSTRAINT_URL" -o "$$TMP_CONSTRAINTS"; then
		echo "ERROR: Cannot download constraints file: $$CONSTRAINT_URL" >&2
		exit 1
	fi

	@if [ ! -s "$$TMP_CONSTRAINTS" ]; then
		echo "ERROR: Constraints file is empty" >&2
		exit 1
	fi

	@python -m pip install --prefer-binary -r docker/airflow/requirements.txt --constraint "$$TMP_CONSTRAINTS"
	@python -m pip install --prefer-binary -r docker/airflow/requirements_dev.txt