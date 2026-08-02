terraform {
  # The CI version is specified by the setup-terraform step in .github/workflows/ci_cd.yml
  required_version = "~> 1.14.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }

    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }

    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }

    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 2.14.0"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = "MyPetProject"
      Environment = "Dev"
      ManagedBy   = "Terraform"
    }
  }
}

provider "snowflake" {
  organization_name = var.snowflake_organization_name
  account_name      = var.snowflake_account_name
  user              = var.snowflake_user
  role              = "TERRAFORM_ROLE"
  authenticator     = "SNOWFLAKE_JWT"
  preview_features_enabled = [
    "snowflake_storage_integration_aws_resource",
    "snowflake_stage_external_s3_resource",
  "snowflake_table_resource"]
}