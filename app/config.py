from __future__ import annotations

import sys

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REQUIRED_VARS = ("BOT_TOKEN", "ADMIN_IDS", "ADMIN_CHAT_ID")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    BOT_TOKEN: str = ""
    ADMIN_IDS: str = ""
    ADMIN_CHAT_ID: int = 0

    DATABASE_URL: str = ""
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    REDIS_URL: str = "redis://redis:6379/0"

    WEBHOOK_URL: str = ""
    WEBHOOK_PATH: str = "/webhook"
    WEBAPP_HOST: str = "0.0.0.0"
    WEBAPP_PORT: int = 8080

    TIMEZONE: str = "Asia/Aqtobe"

    CHANNEL_USERNAME: str = "@historykazakhkz"
    CHANNEL_TITLE: str = "История Казахстана"

    @model_validator(mode="after")
    def _build_database_url_if_missing(self) -> "Settings":
        # If DATABASE_URL wasn't provided explicitly, assemble it from the discrete
        # POSTGRES_* variables (matches the values docker-compose passes to the "db" service).
        if not self.DATABASE_URL and self.POSTGRES_USER and self.POSTGRES_PASSWORD and self.POSTGRES_DB:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        return self

    @property
    def admin_ids(self) -> set[int]:
        return {int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()}


def _load_settings() -> Settings:
    settings = Settings()

    missing = [name for name in REQUIRED_VARS if not getattr(settings, name)]
    if not settings.DATABASE_URL:
        missing.append("DATABASE_URL (or POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB)")

    if missing:
        print(
            "\n"
            "========================================================================\n"
            "ОШИБКА КОНФИГУРАЦИИ: не заданы обязательные переменные окружения:\n"
            f"  {', '.join(missing)}\n"
            "\n"
            "Проверьте:\n"
            "  1. Файл .env лежит рядом с docker-compose.yml (в корне проекта), а не\n"
            "     внутри app/ и не переименован (например, .env.example не переименован в .env).\n"
            "  2. В docker-compose.yml у сервиса 'bot' (и 'migrate') указано 'env_file: .env'.\n"
            "  3. В .env НЕТ пробелов вокруг '=' и кавычек вокруг значений, например:\n"
            "       ADMIN_IDS=111111111,222222222\n"
            "     а не:\n"
            "       ADMIN_IDS = \"111111111,222222222\"\n"
            "  4. После правки .env контейнеры пересозданы: docker compose up -d --build\n"
            "     (простого restart недостаточно, если env_file изменился).\n"
            "  5. Если запускаете 'docker run' вручную, а не docker compose — добавьте\n"
            "     флаг '--env-file .env' к команде docker run.\n"
            "========================================================================\n"
        )
        sys.exit(1)

    return settings


settings = _load_settings()
