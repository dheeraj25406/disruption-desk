from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    database_url: str = "sqlite:///./flyo_disruption.db"
    app_env: str = "development"
    cors_origins: str = "http://localhost:5173"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    @model_validator(mode="after")
    def model_only(self):
        if self.gemini_model != "gemini-3.5-flash-lite":
            raise ValueError("Only gemini-3.5-flash-lite is supported")
        return self
settings = Settings()
