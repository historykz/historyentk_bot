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

    REDIS_URL: str = ""

    WEBHOOK_URL: str = ""
    WEBHOOK_PATH: str = "/webhook"
    WEBAPP_HOST: str = "0.0.0.0"
    WEBAPP_PORT: int = 8080

    TIMEZONE: str = "Asia/Aqtobe"

    CHANNEL_USERNAME: str = "@historykazakhkz"
    CHANNEL_TITLE: str = "История Казахстана"

    @model_validator(mode="after")
    def _strip_whitespace(self) -> "Settings":
        # Guards against values that are technically non-empty (e.g. a stray space left
        # over from editing a Variables field in a hosting dashboard) but useless — these
        # must be treated the same as "not set", not passed through to fail deep inside a
        # library with a cryptic traceback.
        for field in (
            "BOT_TOKEN", "ADMIN_IDS", "DATABASE_URL", "REDIS_URL",
            "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST",
            "WEBHOOK_URL",
        ):
            setattr(self, field, getattr(self, field).strip())
        return self

    @model_validator(mode="after")
    def _build_database_url_if_missing(self) -> "Settings":
        # If DATABASE_URL wasn't provided explicitly, assemble it from the discrete
        # POSTGRES_* variables (matches the values docker-compose passes to the "db" service).
        if not self.DATABASE_URL and self.POSTGRES_USER and self.POSTGRES_PASSWORD and self.POSTGRES_DB:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

        # Managed hosting providers (Railway, Render, Heroku, etc.) hand out DATABASE_URL
        # as plain "postgres://" or "postgresql://" — normalize it to the asyncpg driver
        # scheme our async engine expects, so users don't have to edit it by hand.
        if self.DATABASE_URL.startswith("postgres://"):
            self.DATABASE_URL = "postgresql+asyncpg://" + self.DATABASE_URL[len("postgres://"):]
        elif self.DATABASE_URL.startswith("postgresql://"):
            self.DATABASE_URL = "postgresql+asyncpg://" + self.DATABASE_URL[len("postgresql://"):]

        return self

    @property
    def admin_ids(self) -> set[int]:
        return {int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()}


def _load_settings() -> Settings:
    settings = Settings()

    missing = [name for name in REQUIRED_VARS if not getattr(settings, name)]
    if not settings.DATABASE_URL:
        missing.append("DATABASE_URL (or POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB)")
    elif "://" not in settings.DATABASE_URL:
        # Non-empty but clearly not a real connection string (e.g. leftover garbage from
        # editing the field in a hosting dashboard) — fail with a clear message instead of
        # letting SQLAlchemy crash later with a cryptic traceback.
        print(
            "\n"
            "========================================================================\n"
            f"ОШИБКА КОНФИГУРАЦИИ: DATABASE_URL задан, но не похож на корректную ссылку:\n"
            f"  {settings.DATABASE_URL!r}\n"
            "\n"
            "Ожидается что-то вроде 'postgresql+asyncpg://user:pass@host:5432/dbname'.\n"
            "Откройте переменную DATABASE_URL в панели хостинга, очистите поле полностью\n"
            "и заново подставьте ссылку на переменную сервиса Postgres (в Railway это\n"
            "делается через 'Add Reference' / значок '{}', а не вводом текста руками).\n"
            "========================================================================\n"
        )
        sys.exit(1)

    if missing:
        print(
            "\n"
            "========================================================================\n"
            "ОШИБКА КОНФИГУРАЦИИ: не заданы обязательные переменные окружения:\n"
            f"  {', '.join(missing)}\n"
            "\n"
            "Проверьте:\n"
            "  1. Если вы деплоите через Docker Compose: файл .env лежит рядом с\n"
            "     docker-compose.yml (в корне проекта), а не внутри app/, и не\n"
            "     переименован (например, .env.example не переименован в .env).\n"
            "  2. В docker-compose.yml у сервиса 'bot' (и 'migrate') указано 'env_file: .env'.\n"
            "  3. В .env НЕТ пробелов вокруг '=' и кавычек вокруг значений, например:\n"
            "       ADMIN_IDS=111111111,222222222\n"
            "     а не:\n"
            "       ADMIN_IDS = \"111111111,222222222\"\n"
            "  4. После правки .env контейнеры пересозданы: docker compose up -d --build\n"
            "     (простого restart недостаточно, если env_file изменился).\n"
            "  5. Если запускаете 'docker run' вручную, а не docker compose — добавьте\n"
            "     флаг '--env-file .env' к команде docker run.\n"
            "  6. Если вы деплоите на Railway/Render/Heroku и т.п.: .env-файл там не\n"
            "     используется вообще — переменные задаются в панели управления\n"
            "     хостинга (Variables/Environment) для сервиса бота, а не для\n"
            "     сервисов Postgres/Redis. На Railway для DATABASE_URL и REDIS_URL\n"
            "     удобнее всего использовать 'Add Reference' на переменные\n"
            "     соответствующих сервисов Postgres/Redis в этом же проекте.\n"
            "========================================================================\n"
        )
        sys.exit(1)

    if "redis://redis:" in settings.REDIS_URL or "redis://db:" in settings.REDIS_URL:
        print(
            "ПРЕДУПРЕЖДЕНИЕ: REDIS_URL указывает на хост 'redis'/'db' — это имя сервиса "
            "внутри docker-compose. На управляемом хостинге (Railway и т.п.) такого хоста "
            "не существует, подключение к Redis не удастся. Укажите REDIS_URL реального "
            "Redis-сервиса вашего хостинга."
        )

    return settings


settings = _load_settings()
