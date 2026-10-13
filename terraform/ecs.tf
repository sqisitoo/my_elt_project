# =============================================================================
# ECS.TF — Airflow on ECS Fargate
# =============================================================================
# Everything needed to run Apache Airflow on AWS ECS Fargate:
#
#   1. ECS Cluster & CloudWatch logging
#   2. Security groups (network access for ECS tasks)
#   3. Cryptographic secrets (Fernet, JWT, Flask session key)
#   4. Database & Snowflake locals (connection strings & credentials)
#   5. AWS Secrets Manager (sensitive values stored outside task definition)
#   6. ECS secrets mapping (Secrets Manager → container env vars)
#   7. Airflow environment variables (non-secret, plain-text config)
#   8. ECS task definition (3-container monolith: apiserver, scheduler, dag-processor)
#   9. ECS service (keeps the task running with circuit breaker & Spot pricing)
#
# Architecture decisions:
#   - Fargate (no EC2) — zero server management.
#   - FARGATE_SPOT — ~70% cheaper; acceptable interruption risk for a pet project.
#   - LocalExecutor — no need for Celery + Redis at low DAG concurrency.
#   - Single RDS instance shared by Airflow metadata DB and analytics DWH.
#   - Public subnets + assign_public_ip instead of NAT Gateway (~$32/mo saved).
#   - Airflow task logs shipped to S3; CloudWatch kept at 5-day retention
#     for quick operational debugging only.
# =============================================================================


# -----------------------------------------------------------------------------
# 1. ECS CLUSTER & LOGGING
# -----------------------------------------------------------------------------
# Fargate-only cluster — no EC2 capacity to provision or patch.
# FARGATE_SPOT (weight=100, base=0) routes ALL tasks to Spot by default.
# Spot can be interrupted by AWS with a 30-second warning, which is acceptable
# for a dev/pet-project workload. Switch base=1 to FARGATE (on-demand) if
# you need at least one task guaranteed to be always running.
# -----------------------------------------------------------------------------

resource "aws_ecs_cluster" "airflow" {
  name = "airflow-cluster"

  tags = {
    Name = "airflow-cluster"
  }
}

resource "aws_ecs_cluster_capacity_providers" "airflow" {
  cluster_name = aws_ecs_cluster.airflow.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 0   # No on-demand tasks guaranteed
    weight            = 100 # 100% of tasks go to Spot
    capacity_provider = "FARGATE_SPOT"
  }
}

# Short retention — CloudWatch is only for quick debugging;
# production-grade logs go to S3 via Airflow remote logging (see env vars below).
resource "aws_cloudwatch_log_group" "airflow" {
  name              = "/ecs/airflow"
  retention_in_days = 5
}


# -----------------------------------------------------------------------------
# 2. SECURITY GROUP — Network rules for ECS Airflow tasks
# -----------------------------------------------------------------------------
# A single SG shared by all Airflow containers (apiserver, scheduler
# and dag-processor).
#
# Inbound:  port 8080 (Airflow Web UI) restricted to your IP only
#           (controlled by var.airflow_ui_allowed_cidrs in terraform.tfvars).
# Outbound: fully open — required so tasks can pull Docker images from ECR,
#           reach AWS APIs (S3, Secrets Manager), and connect to RDS.
#
# An additional rule on the RDS SG (rds_sg) allows port 5432 FROM this SG,
# so Airflow tasks can talk to Postgres without opening RDS to the world.
# -----------------------------------------------------------------------------

resource "aws_security_group" "ecs_airflow" {
  name        = "airflow-ecs-sg"
  description = "Security Group for Airflow ECS Tasks (apiserver & scheduler)"
  vpc_id      = aws_vpc.airflow.id

  tags = {
    Name = "airflow-ecs-sg"
  }
}

# Airflow Web UI — only from the CIDRs listed in var.airflow_ui_allowed_cidrs.
resource "aws_security_group_rule" "ingress_apiserver" {
  type              = "ingress"
  security_group_id = aws_security_group.ecs_airflow.id

  from_port = 8080
  to_port   = 8080
  protocol  = "tcp"

  cidr_blocks = var.airflow_ui_allowed_cidrs
  description = "Allow Web UI access from host ip"
}

# Full egress — needed for ECR Docker pull, S3, Secrets Manager, RDS, etc.
resource "aws_security_group_rule" "egress_all" {
  type              = "egress"
  security_group_id = aws_security_group.ecs_airflow.id

  from_port = 0
  to_port   = 0
  protocol  = "-1"

  cidr_blocks = ["0.0.0.0/0"]
  description = "Allow outbound traffic for Docker pull and AWS APIs"
}

# Cross-SG rule: allow ECS tasks → RDS on port 5432.
# Placed on the RDS security group (rds_sg from database.tf) but defined here
# because it logically belongs to the ECS networking context.
resource "aws_security_group_rule" "rds_ingress_from_ecs" {
  type                     = "ingress"
  security_group_id        = aws_security_group.rds_sg.id
  source_security_group_id = aws_security_group.ecs_airflow.id

  from_port   = 5432
  to_port     = 5432
  protocol    = "tcp"
  description = "Allow inbound traffic from ECS Airflow"
}


# -----------------------------------------------------------------------------
# 3. CRYPTOGRAPHIC SECRETS
# -----------------------------------------------------------------------------
# Airflow requires three separate secrets:
#
#   fernet_key  — encrypts sensitive values (Connections, Variables) stored
#                 in the metadata DB. 32 bytes → base64-encoded.
#   jwt_secret  — signs JWT tokens for the REST API authentication.
#   flask_secret — secret key for the Airflow API; signs session cookies
#                  and CSRF tokens in the Web UI.
#
# All three are generated once at `terraform apply` and persist in TF state.
# Rotating them later will invalidate existing sessions / encrypted data.
# -----------------------------------------------------------------------------

resource "random_id" "fernet_key" {
  byte_length = 32
}

resource "random_id" "jwt_secret" {
  byte_length = 32
}

resource "random_password" "flask_secret" {
  length  = 32
  special = true
}

# -----------------------------------------------------------------------------
# 4. DATABASE LOCALS
# -----------------------------------------------------------------------------
# Two connection strings to the same RDS instance, but with different drivers:
#
#   sql_alchemy_conn — used by Airflow internally for its metadata DB.
#                      Requires "postgresql+psycopg2://" because Airflow's
#                      SQLAlchemy layer needs the psycopg2 driver explicitly.
#
#   dwh_conn_string  — passed to DAG code via AIRFLOW_CONN_MY_POSTGRES_DWH.
#                      Uses the plain "postgresql://" scheme (libpq-compatible).
#
# Both point to the same RDS instance to keep costs low in a pet project.
# In production I'd separate the metadata DB from the analytics DWH.
# -----------------------------------------------------------------------------
locals {
  database_endpoint = aws_db_instance.default.address
  database_user     = aws_db_instance.default.username
  database_pass     = random_password.rds_password.result
  database_name     = aws_db_instance.default.db_name

  # Airflow metadata DB connection (SQLAlchemy + psycopg2 driver)
  sql_alchemy_conn = format(
    "postgresql+psycopg2://%s:%s@%s/%s",
    local.database_user,
    local.database_pass,
    local.database_endpoint,
    local.database_name
  )

  # DWH connection for DAGs — injected as AIRFLOW_CONN_MY_POSTGRES_DWH
  dwh_conn_string = format(
    "postgresql://%s:%s@%s/%s",
    local.database_user,
    local.database_pass,
    local.database_endpoint,
    local.database_name
  )
}

# Snowflake service-user credentials — assembled from Snowflake provider
# resources (snowflake.tf) and the generated TLS key pair.
# Two key variants are stored:
#   key     — plain PEM, consumed by dbt (profiles.yml).
#   key_b64 — base64-encoded PEM, consumed by the Airflow Snowflake connection.
locals {
  snowflake_creds = {
    account   = "${var.snowflake_organization_name}-${var.snowflake_account_name}"
    user      = snowflake_service_user.service_user.name
    role      = snowflake_account_role.airflow.name
    database  = snowflake_database.raw_db.name
    warehouse = snowflake_warehouse.tf_warehouse.name
    schema    = snowflake_schema.raw_air_pollution.name
    # plain pem for dbt, encoded for airflow snowflake conn 
    key     = tls_private_key.airflow_svc_key.private_key_pem
    key_b64 = base64encode(tls_private_key.airflow_svc_key.private_key_pem)
  }
}

# -----------------------------------------------------------------------------
# 5. AWS SECRETS MANAGER — sensitive values injected into ECS containers
# -----------------------------------------------------------------------------
# Secrets are NOT passed as plain-text env vars. Instead they are stored in
# Secrets Manager and referenced via the ECS task definition's "secrets" block.
# ECS agent fetches them at container start and exposes as env vars inside
# the container — this way they never appear in the task definition JSON.
#
# Four secrets are used:
#   api_key_secret       — OpenWeather API key (single string).
#   airflow_core_secrets — a JSON blob bundling all Airflow-internal secrets
#                          (DB conn, Fernet key, JWT, Flask key, DWH conn).
#                          Each key in the JSON is extracted individually via
#                          the "secret:jsonKey::" ARN syntax in the ECS secrets
#                          block below.
#   airflow_snowflake    — Snowflake service-user connection stored as a JSON
#                          blob matching the Airflow Connection schema.
#                          Injected whole as AIRFLOW_CONN_SNOWFLAKE_CONN.
#   dbt_snowflake        — Snowflake credentials for dbt (account, user, role,
#                          database, warehouse, schema, private_key_content).
#                          Individual keys are extracted via the same ARN
#                          syntax for SNOWFLAKE_PRIVATE_KEY and SNOWFLAKE_USER.
# -----------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "api_key_secret" {
  name                    = "api/openweather/api_key"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "api_key" {
  secret_id     = aws_secretsmanager_secret.api_key_secret.id
  secret_string = var.openweather_api_key
}

resource "aws_secretsmanager_secret" "airflow_core_secrets" {
  name                    = "airflow/core_secrets"
  description             = "Airflow core secrets and connections"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "airflow_core_secrets_version" {
  secret_id = aws_secretsmanager_secret.airflow_core_secrets.id
  secret_string = jsonencode({
    "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN" = local.sql_alchemy_conn
    "AIRFLOW__API__SECRET_KEY"            = random_password.flask_secret.result
    "AIRFLOW__API_AUTH__JWT_SECRET"       = random_id.jwt_secret.b64_url
    "AIRFLOW__CORE__FERNET_KEY"           = random_id.fernet_key.b64_std
    "AIRFLOW_CONN_MY_POSTGRES_DWH"        = local.dwh_conn_string

    # TODO: deprecate — kept temporarily for legacy DAG code that reads
    # DB_PASSWORD directly instead of using the Airflow Connection.
    "DB_PASSWORD" = random_password.rds_password.result
  })
}

# Snowflake service-user connection — stored in Secrets Manager so the
# private key never appears in the ECS task definition.
resource "aws_secretsmanager_secret" "airflow_snowflake" {
  name                    = "airflow/snowflake/service-user"
  recovery_window_in_days = 0
}

# JSON blob follows Airflow's Connection schema: conn_type, login, schema,
# and an "extra" map with account, warehouse, database, role, and the
# base64-encoded private key for key-pair authentication (no password).
resource "aws_secretsmanager_secret_version" "airflow_snowflake" {
  secret_id = aws_secretsmanager_secret.airflow_snowflake.id
  secret_string = jsonencode({
    "conn_type" = "snowflake"
    "login"     = local.snowflake_creds.user
    "schema"    = local.snowflake_creds.schema
    "extra" = {
      "account"             = local.snowflake_creds.account
      "warehouse"           = local.snowflake_creds.warehouse
      "database"            = local.snowflake_creds.database
      "role"                = local.snowflake_creds.role
      "private_key_content" = local.snowflake_creds.key_b64
    }
  })
}

# dbt Snowflake credentials — a JSON blob with account, user, role, database,
# warehouse, schema, and the plain PEM private key (not base64). Individual
# keys are extracted in the ECS secrets mapping (section 6) for SNOWFLAKE_PRIVATE_KEY
# and SNOWFLAKE_USER env vars consumed by dbt.
resource "aws_secretsmanager_secret" "dbt_snowflake" {
  name                    = "airflow/snowflake/dbt_parameters"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "dbt_snowflake" {
  secret_id = aws_secretsmanager_secret.dbt_snowflake.id
  secret_string = jsonencode({
    "account"             = local.snowflake_creds.account
    "user"                = local.snowflake_creds.user
    "role"                = local.snowflake_creds.role
    "database"            = local.snowflake_creds.database
    "warehouse"           = local.snowflake_creds.warehouse
    "schema"              = local.snowflake_creds.schema
    "private_key_content" = local.snowflake_creds.key
  })
}
# -----------------------------------------------------------------------------
# 6. ECS SECRETS MAPPING — wires Secrets Manager → container env vars
# -----------------------------------------------------------------------------
# ECS "secrets" use the ARN + JSON-key syntax to extract individual values
# from the bundled airflow_core_secrets JSON secret. Format:
#   "<secret-arn>:<json-key>::"  (version-stage and version-id left empty
#                                 to always pull the AWSCURRENT version).
#
# API_KEY is a standalone secret (single string, not JSON), so it uses
# the plain ARN without a JSON-key suffix.
#
# AIRFLOW_CONN_SNOWFLAKE_CONN also uses the plain ARN — ECS injects the
# entire JSON blob as a single env var, and Airflow parses it natively
# as a Connection URI.
#
# SNOWFLAKE_PRIVATE_KEY and SNOWFLAKE_USER are extracted from the
# dbt_snowflake JSON secret using the same ARN + JSON-key syntax.
# -----------------------------------------------------------------------------
locals {
  airflow_secrets_arn = aws_secretsmanager_secret.airflow_core_secrets.arn
  dbt_secrets_arn     = aws_secretsmanager_secret.dbt_snowflake.arn
  airflow_secrets = [
    { name = "API_KEY", valueFrom = aws_secretsmanager_secret.api_key_secret.arn },
    {
      name      = "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN",
      valueFrom = "${local.airflow_secrets_arn}:AIRFLOW__DATABASE__SQL_ALCHEMY_CONN::"
    },
    {
      name      = "AIRFLOW__API__SECRET_KEY",
      valueFrom = "${local.airflow_secrets_arn}:AIRFLOW__API__SECRET_KEY::"
    },
    {
      name      = "AIRFLOW__API_AUTH__JWT_SECRET",
      valueFrom = "${local.airflow_secrets_arn}:AIRFLOW__API_AUTH__JWT_SECRET::"
    },
    {
      name      = "AIRFLOW__CORE__FERNET_KEY",
      valueFrom = "${local.airflow_secrets_arn}:AIRFLOW__CORE__FERNET_KEY::"
    },
    {
      name      = "AIRFLOW_CONN_MY_POSTGRES_DWH",
      valueFrom = "${local.airflow_secrets_arn}:AIRFLOW_CONN_MY_POSTGRES_DWH::"
    },
    {
      name      = "DB_PASSWORD",
      valueFrom = "${local.airflow_secrets_arn}:DB_PASSWORD::"
    },
    {
      name      = "AIRFLOW_CONN_SNOWFLAKE_CONN",
      valueFrom = aws_secretsmanager_secret.airflow_snowflake.arn
    },
    {
      name      = "SNOWFLAKE_PRIVATE_KEY",
      valueFrom = "${local.dbt_secrets_arn}:private_key_content::"
    },
    {
      name      = "SNOWFLAKE_USER",
      valueFrom = "${local.dbt_secrets_arn}:user::"
    }
  ]
}
# -----------------------------------------------------------------------------
# 7. AIRFLOW ENVIRONMENT VARIABLES (non-secret, plain-text)
# -----------------------------------------------------------------------------
# These are safe to pass as plain env vars — no credentials here.
# Sensitive values (DB password, Fernet key, etc.) are in the "secrets" block.
#
# Key design decisions:
#   - LocalExecutor: sufficient for a pet-project with low DAG concurrency;
#     avoids running a separate Celery worker + Redis broker.
#   - LOAD_EXAMPLES=false: keeps the Airflow UI clean.
#   - DAGS_ARE_PAUSED_AT_CREATION=true: new DAGs won't fire until you
#     explicitly unpause them — prevents surprise runs after deploy.
#   - FabAuthManager: pluggable auth backend (Airflow 3), backed by
#     Flask-AppBuilder.
#   - Remote logging to S3: task logs persist beyond Fargate task lifecycle.
#   - AIRFLOW_CONN_AWS_DEFAULT="aws://": tells Airflow to use the task role's
#     IAM credentials for all AWS operations (S3 logging, etc.) — no
#     static AWS keys needed.
#   - Snowflake non-secret vars (account, database, role, schema,
#     warehouse): passed as plain env vars for dbt and DAG code.
#   - DBT_* vars: dbt target, profiles dir, and project dir for the
#     dbt CLI invoked by Airflow DAGs.
#   - DB_* vars: passed for legacy DAG code that constructs its own
#     connection instead of using the Airflow Connection object.
# -----------------------------------------------------------------------------
locals {
  airflow_env_vars = [
    # --- Airflow core config ---
    { name = "AIRFLOW__CORE__EXECUTOR", value = "LocalExecutor" },
    { name = "AIRFLOW__CORE__LOAD_EXAMPLES", value = "false" },
    { name = "AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION", value = "true" },
    { name = "AIRFLOW__SCHEDULER__ENABLE_HEALTH_CHECK", value = "true" },
    { name = "AIRFLOW__CORE__AUTH_MANAGER", value = "airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager" },

    # When true, the scheduler auto-creates DagRun data intervals for
    # cron-based schedules on first unpause, backfilling any missed intervals
    # since the DAG's start_date.
    { name = "AIRFLOW__SCHEDULER__CREATE_CRON_DATA_INTERVALS", value = "true" },

    # --- Remote logging (S3) ---
    { name = "AIRFLOW__LOGGING__REMOTE_LOGGING", value = "true" },
    { name = "AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER", value = "s3://${aws_s3_bucket.datalake.bucket}/airflow-logs" },
    { name = "AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID", value = "aws_default" },

    # "aws://" = use IAM task role credentials, no static keys.
    { name = "AIRFLOW_CONN_AWS_DEFAULT", value = "aws://" },

    # --- RDS connection details (non-secret parts) ---
    # DB_PASSWORD is injected separately via the secrets block.
    { name = "DB_HOST", value = aws_db_instance.default.address },
    { name = "DB_PORT", value = tostring(aws_db_instance.default.port) },
    { name = "DB_NAME", value = aws_db_instance.default.db_name },
    { name = "DB_USER", value = aws_db_instance.default.username },

    # --- Application-specific config ---
    { name = "API_BASE_URL", value = var.api_base_url },
    { name = "PYTHONPATH", value = "/opt/airflow" },
    { name = "AWS_S3_BUCKET_NAME", value = aws_s3_bucket.datalake.bucket },
    { name = "AWS_REGION", value = var.aws_region },

    # --- Snowflake ---
    { name = "SNOWFLAKE_ACCOUNT", value = local.snowflake_creds.account },
    { name = "SNOWFLAKE_DATABASE", value = local.snowflake_creds.database },
    { name = "SNOWFLAKE_ROLE", value = local.snowflake_creds.role },
    { name = "SNOWFLAKE_SCHEMA", value = local.snowflake_creds.schema },
    { name = "SNOWFLAKE_WAREHOUSE", value = local.snowflake_creds.warehouse },

    { name = "DBT_TARGET", value = var.dbt_target },
    { name = "DBT_PROFILES_DIR", value = var.dbt_profiles_dir },
    { name = "DBT_PROJECT_DIR", value = var.dbt_project_dir }
  ]
}

# -----------------------------------------------------------------------------
# 8. ECS TASK DEFINITION — "monolith" with 3 sidecar containers
# -----------------------------------------------------------------------------
# A single Fargate task runs three containers sharing the same network
# namespace (awsvpc mode):
#
#   airflow-apiserver     — serves the Web UI on port 8080.
#   airflow-scheduler     — runs `db migrate`, creates the admin user on
#                           first boot, then starts the scheduler loop.
#   airflow-dag-processor — parses DAG files independently from the
#                           scheduler (Airflow 3 standalone DAG processor).
#
# All three share the same env vars and secrets. Only the apiserver
# exposes a port. All containers are marked essential=true, so if any
# one crashes the entire task is replaced — keeps the system consistent.
#
# linuxParameters.initProcessEnabled = true: runs a tiny init (PID 1)
# inside each container so zombie processes are reaped properly.
#
# Resource sizing (cpu=512, memory=3072):
#   0.5 vCPU + 3 GB RAM — the smallest practical config for running
#   3 Airflow processes in one task. Scale up if OOM-killed.
# -----------------------------------------------------------------------------
resource "aws_ecs_task_definition" "airflow_monolith" {
  family                   = "airflow-monolith"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"  # 0.5 vCPU
  memory                   = "3072" # 3 GB RAM
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.airflow_task_role.arn

  container_definitions = jsonencode([
    # --- Container 1: API Server (Web UI) ---
    {
      name      = "airflow-apiserver"
      image     = "${aws_ecr_repository.airflow.repository_url}:latest"
      essential = true
      command   = ["api-server"]

      portMappings = [
        {
          containerPort = 8080
          hostPort      = 8080
          protocol      = "tcp"
        }
      ]

      environment = local.airflow_env_vars
      secrets     = local.airflow_secrets

      linuxParameters = {
        initProcessEnabled = true
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.airflow.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "apiserver"
        }
      }
    },

    # --- Container 2: Scheduler (+ DB bootstrap on first run) ---
    # On startup: migrate DB schema → create admin user (idempotent) → run scheduler.
    # The "|| echo" fallback prevents a non-zero exit if the user already exists.
    {
      name       = "airflow-scheduler"
      image      = "${aws_ecr_repository.airflow.repository_url}:latest"
      essential  = true
      entryPoint = ["/bin/bash"]
      command = [
        "-c",
        "airflow db migrate && (airflow users create --username admin --password admin --firstname Admin --lastname User --role Admin --email admin@example.com || echo 'User already exists, skipping creation') && airflow scheduler"
      ]

      environment = local.airflow_env_vars
      secrets     = local.airflow_secrets

      linuxParameters = {
        initProcessEnabled = true
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.airflow.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "scheduler"
        }
      }
    },

    # --- Container 3: Standalone DAG Processor (Airflow 3) ---
    # Offloads DAG file parsing from the scheduler, improving scheduling
    # latency. A first-class component in Airflow 3.
    {
      name      = "airflow-dag-processor"
      image     = "${aws_ecr_repository.airflow.repository_url}:latest"
      essential = true
      command   = ["dag-processor"]

      environment = local.airflow_env_vars
      secrets     = local.airflow_secrets

      linuxParameters = {
        initProcessEnabled = true
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.airflow.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "dag-processor"
        }
      }
    }
  ])
}



# -----------------------------------------------------------------------------
# 9. ECS SERVICE — keeps the monolith task running
# -----------------------------------------------------------------------------
# desired_count=1: no HA — a single replica is fine for a pet project.
# enable_execute_command=true: allows `aws ecs execute-command` to SSH
# into a running container for debugging (requires the SSM policy on the
# task role, defined in iam.tf).
# -----------------------------------------------------------------------------
resource "aws_ecs_service" "airflow_service" {
  name                   = "airflow-main-service"
  cluster                = aws_ecs_cluster.airflow.id
  task_definition        = aws_ecs_task_definition.airflow_monolith.arn
  desired_count          = 1
  enable_execute_command = true

  # Use capacity_provider_strategy instead of launch_type so we can
  # leverage FARGATE_SPOT pricing (~70% cheaper than on-demand).
  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 100
    base              = 0
  }

  network_configuration {
    subnets         = [aws_subnet.public_1.id, aws_subnet.public_2.id]
    security_groups = [aws_security_group.ecs_airflow.id]

    # CRITICAL: must be true in a public subnet without a NAT Gateway.
    # Without a public IP the task cannot reach the internet (ECR, S3, etc.).
    assign_public_ip = true
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  # Circuit breaker: if a new deployment keeps crashing, ECS stops retrying
  # and rolls back to the last stable version automatically.
  # Saves money and avoids infinite restart loops.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}

