from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: str
    ADMIN_IDS: str
    ADMIN_CHAT_ID: int

    DATABASE_URL: str
    REDIS_URL: str = "redis://redis:6379/0"

    WEBHOOK_URL: str = ""
    WEBHOOK_PATH: str = "/webhook"
    WEBAPP_HOST: str = "0.0.0.0"
    WEBAPP_PORT: int = 8080

    TIMEZONE: str = "Asia/Aqtobe"

    CHANNEL_USERNAME: str = "@historykazakhkz"
    CHANNEL_TITLE: str = "История Казахстана"

    @property
    def admin_ids(self) -> set[int]:
        return {int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()}


settings = Settings()
