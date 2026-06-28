resource "snowflake_database" "raw_db" {
  name         = "RAW"
  is_transient = false
}

resource "snowflake_database" "analytic_db" {
  name         = "ANALYTICS"
  is_transient = false
}

resource "snowflake_schema" "raw_air_pollution" {
  database = snowflake_database.raw_db.name
  name     = "AIR_POLLUTION"
}

resource "snowflake_schema" "raw_weather" {
  database = snowflake_database.raw_db.name
  name     = "WEATHER"
}


resource "snowflake_warehouse" "tf_warehouse" {
  name                      = "SNOWFLAKE_WH"
  warehouse_type            = "STANDARD"
  warehouse_size            = "XSMALL"
  max_cluster_count         = 1
  min_cluster_count         = 1
  auto_suspend              = 60
  auto_resume               = true
  enable_query_acceleration = false
  initially_suspended       = true
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "snowflake_role" {
  name = "snowflake-s3-role"

  assume_role_policy = jsonencode(
    length(var.snowflake_external_id) == 0 ?
    {
      Version = "2012-10-17"
      Statement = [{
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action    = "sts:AssumeRole"
        Condition = {}
      }]
    } :
    {
      Version = "2012-10-17"
      Statement = [{
        Effect = "Allow"
        Principal = {
          AWS = var.snowflake_iam_user_arn
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "sts:ExternalId" = var.snowflake_external_id
          }
        }
      }]
    }
  )
}

resource "aws_iam_role_policy_attachment" "snowflake_s3" {
  role       = aws_iam_role.snowflake_role.name
  policy_arn = aws_iam_policy.s3_access.arn
}

resource "snowflake_storage_integration_aws" "s3_storage_integration" {
  name                      = "aws_storage_integration"
  enabled                   = true
  storage_provider          = "S3"
  storage_allowed_locations = ["s3://${aws_s3_bucket.datalake.id}"]
  storage_aws_role_arn      = aws_iam_role.snowflake_role.arn
}

resource "snowflake_stage_external_s3" "stage_external_s3_air_pollution" {
  name                = "s3_stage"
  database            = snowflake_database.raw_db.name
  schema              = snowflake_schema.raw_air_pollution.name
  url                 = "s3://${aws_s3_bucket.datalake.id}"
  storage_integration = snowflake_storage_integration_aws.s3_storage_integration.name

}

resource "snowflake_stage_external_s3" "stage_external_s3_weather" {
  name                = "s3_stage"
  database            = snowflake_database.raw_db.name
  schema              = snowflake_schema.raw_weather.name
  url                 = "s3://${aws_s3_bucket.datalake.id}"
  storage_integration = snowflake_storage_integration_aws.s3_storage_integration.name

}

resource "snowflake_table" "raw_air_pollution" {
  database = snowflake_database.raw_db.name
  schema   = snowflake_schema.raw_air_pollution.name
  name     = "RAW_AIR_POLLUTION"
  comment  = "Raw JSON payloads for air pollution data"

  column {
    name     = "RAW_PAYLOAD"
    type     = "VARIANT"
    nullable = false
  }

  column {
    name     = "_RAW_LOADED_AT"
    type     = "TIMESTAMP_NTZ(9)"
    nullable = false
    default {
      expression = "SYSDATE()"
    }
  }

  column {
    name     = "_SOURCE_FILE"
    type     = "VARCHAR"
    nullable = false
  }
}

resource "snowflake_table" "raw_weather" {
  database = snowflake_database.raw_db.name
  schema   = snowflake_schema.raw_weather.name
  name     = "RAW_WEATHER"
  comment  = "Raw JSON payloads for weather data"

  column {
    name     = "RAW_PAYLOAD"
    type     = "VARIANT"
    nullable = false
  }

  column {
    name     = "_RAW_LOADED_AT"
    type     = "TIMESTAMP_NTZ(9)"
    nullable = false
    default {
      expression = "SYSDATE()"
    }
  }

  column {
    name     = "_SOURCE_FILE"
    type     = "VARCHAR"
    nullable = false
  }
}

resource "tls_private_key" "airflow_svc_key" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "snowflake_account_role" "airflow" {
  name = "AIRFLOW_ROLE"
}

resource "snowflake_service_user" "service_user" {
  name = "AIRFLOW_SVC"

  default_warehouse = snowflake_warehouse.tf_warehouse.name
  default_role      = snowflake_account_role.airflow.name

  rsa_public_key = tls_private_key.airflow_svc_key.public_key_pem
}

resource "snowflake_grant_account_role" "airflow_service_user" {
  role_name = snowflake_account_role.airflow.name
  user_name = snowflake_service_user.service_user.name
}

resource "snowflake_grant_privileges_to_account_role" "airflow_wh" {
  account_role_name = snowflake_account_role.airflow.name
  privileges        = ["USAGE", "OPERATE"]

  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.tf_warehouse.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "airflow_db" {
  account_role_name = snowflake_account_role.airflow.name
  privileges        = ["USAGE"]

  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.raw_db.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "airflow_air_pollution_schema_usage" {

  account_role_name = snowflake_account_role.airflow.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW", "CREATE STAGE"]

  on_schema {
    schema_name = "${snowflake_database.raw_db.name}.${snowflake_schema.raw_air_pollution.name}"
  }
}

resource "snowflake_grant_privileges_to_account_role" "airflow_weather_schema_usage" {

  account_role_name = snowflake_account_role.airflow.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW", "CREATE STAGE"]

  on_schema {
    schema_name = "${snowflake_database.raw_db.name}.${snowflake_schema.raw_weather.name}"
  }
}

resource "snowflake_grant_privileges_to_account_role" "airflow_air_pollution_tables_usage" {

  account_role_name = snowflake_account_role.airflow.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]

  on_schema_object {
    all {
      object_type_plural = "TABLES"
      in_schema          = "${snowflake_database.raw_db.name}.${snowflake_schema.raw_air_pollution.name}"
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "airflow_weather_tables_usage" {

  account_role_name = snowflake_account_role.airflow.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]

  on_schema_object {
    all {
      object_type_plural = "TABLES"
      in_schema          = "${snowflake_database.raw_db.name}.${snowflake_schema.raw_weather.name}"
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "airflow_air_pollution_tables_usage_feature" {

  account_role_name = snowflake_account_role.airflow.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]

  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = "${snowflake_database.raw_db.name}.${snowflake_schema.raw_air_pollution.name}"
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "airflow_weather_tables_usage_feature" {

  account_role_name = snowflake_account_role.airflow.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]

  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = "${snowflake_database.raw_db.name}.${snowflake_schema.raw_weather.name}"
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "airflow_air_pollution_stage" {
  account_role_name = snowflake_account_role.airflow.name
  privileges        = ["USAGE", "READ"]

  on_schema_object {
    object_type = "STAGE"
    object_name = "${snowflake_database.raw_db.name}.${snowflake_schema.raw_air_pollution.name}.${snowflake_stage_external_s3.stage_external_s3_air_pollution.name}"
  }
}

resource "snowflake_grant_privileges_to_account_role" "airflow_weather_stage" {
  account_role_name = snowflake_account_role.airflow.name
  privileges        = ["USAGE", "READ"]

  on_schema_object {
    object_type = "STAGE"
    object_name = "${snowflake_database.raw_db.name}.${snowflake_schema.raw_weather.name}.${snowflake_stage_external_s3.stage_external_s3_weather.name}"
  }
}

output "snowflake_iam_user_export" {
  description = "Command to set the Snowflake IAM user ARN as an environment variable"
  value       = "export TF_VAR_snowflake_iam_user_arn='${snowflake_storage_integration_aws.s3_storage_integration.describe_output[0].iam_user_arn}'"
}

output "snowflake_external_id_export" {
  description = "Command to set the Snowflake External ID as an environment variable"
  value       = "export TF_VAR_snowflake_external_id='${snowflake_storage_integration_aws.s3_storage_integration.describe_output[0].external_id}'"
}