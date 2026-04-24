from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    odds_api_key: str = ""
    rapidapi_key: str = ""
    football_data_api_key: str = ""
    anthropic_api_key: str = ""

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    balldontlie_api_key: str = ""
    upstash_redis_url: str = ""
    upstash_redis_token: str = ""
    admin_token: str = ""

    environment: str = "development"
    backend_url: str = "http://localhost:8000"

    class Config:
        env_file = "../.env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
