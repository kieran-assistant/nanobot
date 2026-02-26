# nanobot/config.py
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = Field(..., alias="DATABASE_URL")
    db_name: str = Field(default="nanobot_prod", alias="DATABASE_NAME")
    db_user: str = Field(default="postgres", alias="DB_USER")
    db_password: str = Field(default="password", alias="DB_PASSWORD")
    db_host: str = Field(default="localhost", alias="DB_HOST")
    db_port: int = Field(default=5432, alias="DB_PORT")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
