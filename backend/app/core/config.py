from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


# Resolve the local backend config from this module, not the process working
# directory. `uvicorn app.main:app` is commonly started from either the repo
# root or `backend/`; relative env_file paths silently miss the key in one of
# those launch modes.
BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    airlabs_api_key: str = ""
    airlabs_base_url: str = "https://airlabs.co"
    database_url: str = "sqlite:///./flyo_disruption.db"
    app_env: str = "development"
    cors_origins: str = "http://localhost:5173"
    cors_origin_regex: str = ""
    model_config = SettingsConfigDict(env_file=BACKEND_ENV_FILE, extra="ignore")
    @model_validator(mode="after")
    def model_only(self):
        if self.gemini_model != "gemini-3.5-flash-lite":
            raise ValueError("Only gemini-3.5-flash-lite is supported")
        return self
settings = Settings()
