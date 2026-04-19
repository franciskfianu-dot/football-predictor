from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import json


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Football Predictor API"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # API Keys
    OPENWEATHER_API_KEY: str = ""

    # Admin
    ADMIN_SECRET_TOKEN: str = "change_me"

    # MLflow
    MLFLOW_TRACKING_URI: str = "http://localhost:5001"

    # Scraping
    SCRAPE_DELAY_SECONDS: float = 3.0
    SCRAPE_RETRY_COUNT: int = 3
    SCRAPE_CACHE_TTL_SECONDS: int = 21600  # 6 hours

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173"

    # Google Sheets
    GOOGLE_SERVICE_ACCOUNT_JSON: str = "{}"

    # Model storage
    MODEL_STORAGE_PATH: str = "./model_storage"

    # Leagues (phase 1)
    SUPPORTED_LEAGUES: List[str] = [
        "epl",
        "laliga",
        "seriea",
        "bundesliga",
        "ligue1",
    ]

    # Training config
    MIN_SEASONS_HISTORY: int = 3
    OPTUNA_TRIALS: int = 50
    BACKTEST_SEASONS: int = 1
    CV_FOLDS: int = 5

    @field_validator("CELERY_BROKER_URL", mode="before")
    @classmethod
    def set_celery_broker(cls, v, info):
        return v or info.data.get("REDIS_URL", "redis://localhost:6379/0")

    @field_validator("CELERY_RESULT_BACKEND", mode="before")
    @classmethod
    def set_celery_backend(cls, v, info):
        return v or info.data.get("REDIS_URL", "redis://localhost:6379/0")

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def google_service_account_dict(self) -> dict:
        try:
            return json.loads(self.GOOGLE_SERVICE_ACCOUNT_JSON)
        except Exception:
            return {}

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
