from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class _AWSSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AWS_", extra="ignore")

    access_key_id: str | None = None
    secret_access_key: SecretStr | None = None
    s3_bucket_name: str
    region: Literal["eu-north-1", "eu-central-1", "eu-west-1", "eu-west-2", "eu-west-3"] = "eu-north-1"


class _APISettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="API_", extra="ignore")

    base_url: HttpUrl
    key: SecretStr

    @property
    def url_str(self):
        return str(self.base_url).rstrip("/")


class _DBTSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DBT_", extra="ignore")

    venv_path: str = "/opt/airflow/dbt-venv"
    profiles_dir: str
    project_dir: str

    @computed_field
    def bin_path(self) -> Path:
        return Path(self.venv_path) / "bin" / "dbt"


class Settings(BaseModel):
    aws: _AWSSettings = Field(default_factory=_AWSSettings)
    api: _APISettings = Field(default_factory=_APISettings)
    dbt: _DBTSettings = Field(default_factory=_DBTSettings)


settings = Settings()
