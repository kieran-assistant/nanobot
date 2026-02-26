# nanobot/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = Field(..., alias="DATABASE_URL")
    db_name: str = Field(default="nanobot_prod", alias="DATABASE_NAME")
    db_user: str = Field(default="postgres", alias="DB_USER")
    db_password: str = Field(default="password", alias="DB_PASSWORD")
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")
    deploy_mode: Literal["docker", "external"] = Field(default="docker", alias="DEPLOY_MODE")
    evolution_phase: Literal["phase1", "phase2", "phase3"] = Field(default="phase1", alias="EVOLUTION_PHASE")
    live_mode: bool = Field(default=True, alias="LIVE_MODE")
    planner_usage_cap: int = Field(default=50, alias="PLANNER_USAGE_CAP")
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    workspace_root: str = Field(default=".", alias="WORKSPACE_ROOT")
    security_allowlist_extra: str = Field(default="", alias="SECURITY_ALLOWLIST_EXTRA")
    security_blocklist_extra: str = Field(default="", alias="SECURITY_BLOCKLIST_EXTRA")
    health_report_frequency_days: int = Field(default=7, alias="HEALTH_REPORT_FREQUENCY_DAYS")
    metrics_retention_days: int = Field(default=30, alias="METRICS_RETENTION_DAYS")

settings = Settings()
