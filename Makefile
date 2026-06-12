.ONESHELL:
.PHONY: lint test build check install_deps
SHELL:= /bin/bash

AIRFLOW_VERSION ?= 3.1.6
PYTHON_VERSION ?= 3.10

lint:
	@set -eo pipefail
	ruff check .
	ruff format . --check
	mypy .

test:
	pytest

check: lint test

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