from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/app/backups"))
KEEP_LAST_N = 14


class BackupError(Exception):
    pass


@dataclass
class DbConnInfo:
    user: str
    password: str
    host: str
    port: int
    dbname: str


def _parse_database_url() -> DbConnInfo:
    # settings.DATABASE_URL looks like: postgresql+asyncpg://user:pass@host:port/dbname
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(url)
    if not parsed.hostname or not parsed.path.lstrip("/"):
        raise BackupError("Не удалось разобрать DATABASE_URL для резервного копирования.")
    return DbConnInfo(
        user=parsed.username or "",
        password=parsed.password or "",
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
    )


async def _run(cmd: list[str], env: dict, input_bytes: bytes | None = None) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if input_bytes is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(input=input_bytes), timeout=300)
    except asyncio.TimeoutError:
        proc.kill()
        raise BackupError("Операция с базой данных заняла слишком много времени и была прервана.")
    return proc.returncode, stdout, stderr


def _backup_filename() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return BACKUP_DIR / f"backup_{stamp}.sql"


async def create_backup() -> Path:
    """Runs pg_dump and writes a plain-SQL backup file to BACKUP_DIR. Returns the file path."""
    info = _parse_database_url()
    out_path = _backup_filename()

    env = os.environ.copy()
    env["PGPASSWORD"] = info.password

    cmd = [
        "pg_dump",
        "-h", info.host,
        "-p", str(info.port),
        "-U", info.user,
        "-d", info.dbname,
        "--no-owner",
        "--no-privileges",
        "-F", "p",
    ]
    code, stdout, stderr = await _run(cmd, env)
    if code != 0:
        raise BackupError(f"pg_dump завершился с ошибкой: {stderr.decode(errors='replace')[:500]}")

    out_path.write_bytes(stdout)
    _prune_old_backups()
    logger.info("Backup created: %s (%d bytes)", out_path, len(stdout))
    return out_path


def _prune_old_backups() -> None:
    backups = sorted(BACKUP_DIR.glob("backup_*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[KEEP_LAST_N:]:
        try:
            old.unlink()
        except OSError:
            logger.warning("Failed to remove old backup %s", old)


def list_backups() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("backup_*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)


async def restore_backup(sql_bytes: bytes) -> None:
    """Restores the database from a plain-SQL dump produced by create_backup().

    This is destructive: existing data for objects present in the dump will be
    overwritten/recreated. Callers must confirm with the admin before calling this.
    """
    info = _parse_database_url()
    env = os.environ.copy()
    env["PGPASSWORD"] = info.password

    cmd = [
        "psql",
        "-h", info.host,
        "-p", str(info.port),
        "-U", info.user,
        "-d", info.dbname,
        "-v", "ON_ERROR_STOP=1",
    ]
    code, stdout, stderr = await _run(cmd, env, input_bytes=sql_bytes)
    if code != 0:
        raise BackupError(f"Восстановление завершилось с ошибкой: {stderr.decode(errors='replace')[:800]}")
    logger.info("Database restored from uploaded backup (%d bytes)", len(sql_bytes))


async def scheduled_backup_loop(interval_seconds: int = 24 * 3600) -> None:
    """Background task: creates a backup on startup and then once per interval.
    Runs for the lifetime of the process; any single failure is logged and does not
    stop the loop (so a transient DB hiccup can't silently kill future backups)."""
    while True:
        try:
            await create_backup()
        except Exception:
            logger.exception("Scheduled backup failed")
        await asyncio.sleep(interval_seconds)
