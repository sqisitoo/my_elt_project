-- Run this once, as ACCOUNTADMIN, before the first `terraform apply`.
-- It creates the identity Terraform itself uses; everything else in Snowflake
-- is then managed by terraform/snowflake.tf.
--
-- Prerequisites:
-- 1. Generate an RSA key pair (unencrypted — the Terraform provider and dbt are
--    both configured without a passphrase in this project):
--      openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out keys/snowflake_tf_snow_key.p8 -nocrypt
--      openssl rsa -in keys/snowflake_tf_snow_key.p8 -pubout -out keys/snowflake_tf_snow_key.pub
-- 2. Paste only the base64 body of the .pub file below — the BEGIN/END lines
--    are already in place.
-- 3. Keep the private key out of git (keys/ is gitignored) and export it for
--    the provider:  export SNOWFLAKE_PRIVATE_KEY="$(cat keys/snowflake_tf_snow_key.p8)"

USE ROLE ACCOUNTADMIN;

CREATE USER TERRAFORM_SVC
    TYPE = SERVICE
    COMMENT = "Service user for Terraforming Snowflake"
    RSA_PUBLIC_KEY = "-----BEGIN PUBLIC KEY-----
<PASTE THE CONTENTS OF keys/snowflake_tf_snow_key.pub HERE>
-----END PUBLIC KEY-----";

CREATE ROLE TERRAFORM_ROLE;

GRANT ROLE SYSADMIN TO ROLE TERRAFORM_ROLE;
GRANT ROLE SECURITYADMIN TO ROLE TERRAFORM_ROLE;

GRANT ROLE TERRAFORM_ROLE TO USER TERRAFORM_SVC;
GRANT CREATE INTEGRATION ON ACCOUNT TO ROLE TERRAFORM_ROLE;

ALTER USER TERRAFORM_SVC
SET DEFAULT_ROLE = TERRAFORM_ROLE;

-- Run this query to get your Snowflake account identifiers
-- These values are needed for Terraform provider configuration
SELECT 
    LOWER(CURRENT_ORGANIZATION_NAME()) as organization_name,
    LOWER(CURRENT_ACCOUNT_NAME()) as account_name;