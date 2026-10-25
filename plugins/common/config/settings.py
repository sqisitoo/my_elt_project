from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class _AWSSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AWS_", extra="ignore")

    # Only the bucket is read here. Credentials and region reach boto3 through the
    # aws_default connection (S3Hook), not through settings.
    s3_bucket_name: str


class _APISettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="API_", extra="ignore")

    base_url: HttpUrl
    key: SecretStr

    @property
    def url_str(self):
        return str(self.base_url).rstrip("/")


class _DBTSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DBT_", extra="ignore")

    # MUST match ENV DBT_VENV_PATH in docker/airflow/Dockerfile, where the venv is
    # created. In the image the ENV wins; the default only lets settings import
    # outside it (e.g. pytest in CI). Change both together.
    venv_path: str = "/opt/airflow/dbt_venv"
    profiles_dir: str
    project_dir: str
    # The targets defined in dbt_project/profiles.yml.
    target: Literal["dev", "prod", "ci"]

    @computed_field
    def bin_path(self) -> Path:
        return Path(self.venv_path) / "bin" / "dbt"


class Settings(BaseModel):
    aws: _AWSSettings = Field(default_factory=_AWSSettings)
    api: _APISettings = Field(default_factory=_APISettings)
    dbt: _DBTSettings = Field(default_factory=_DBTSettings)


settings = Settings()
