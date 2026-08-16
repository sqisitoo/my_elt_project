variable "aws_region" {
  description = "AWS Region to deploy on"
  default     = "eu-north-1"
}

variable "aws_profile" {
  description = "AWS CLI Profile"
  default     = "my-pet-project"
}

variable "enable_nat_gateway" {
  description = "Enable NAT Gateway?"
  type        = bool
  default     = false
}

variable "create_bastion" {
  description = "Create Bastion Host for DB access?"
  type        = bool
  default     = false
}

variable "allowed_ssh_cidrs" {
  description = "List of IPs to access the bastion"
  type        = list(string)
  default     = []
}

variable "api_base_url" {
  description = "OpenWeather API endpoint"
  type        = string
}

variable "openweather_api_key" {
  description = "OpenWeather API Key"
  type        = string
  sensitive   = true
}

# snowflake variables
variable "snowflake_organization_name" {
  description = "snowflake organization name"
  type        = string
}

variable "snowflake_account_name" {
  description = "snowflake account name"
  type        = string
}

variable "snowflake_user" {
  description = "snowflake service user with rolles needed for account management"
  type        = string
  default     = "TERRAFORM_SVC"
}

variable "snowflake_iam_user_arn" {
  description = "The ARN of the Snowflake-generated IAM user used to assume the AWS role for S3 access. Leave empty for initial creation."
  type        = string
  default     = ""
}

variable "snowflake_external_id" {
  description = "The External ID provided by Snowflake for the IAM role trust policy. Leave empty for initial creation."
  type        = string
  default     = ""
}

# dbt variables
variable "dbt_target" {
  description = "dbt target environment (e.g. prod, dev)"
  type        = string
  default     = "prod"
}

variable "dbt_profiles_dir" {
  description = "Path to the dbt profiles directory inside the container"
  type        = string
  default     = "/opt/airflow/dbt_project"
}

variable "dbt_project_dir" {
  description = "Path to the dbt project directory inside the container"
  type        = string
  default     = "/opt/airflow/dbt_project"
}

# github variables
variable "github_repository" {
  description = "owner/name of the repository allowed to assume the deploy role via OIDC. A fork must change this or its workflow cannot deploy."
  type        = string
  default     = "sqisitoo/my_elt_project"
}

variable "github_deploy_branch" {
  description = "Branch whose workflow runs may assume the deploy role"
  type        = string
  default     = "main"
}
