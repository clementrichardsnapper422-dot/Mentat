from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    vast_api_key: str | None
    manager_token: str | None
    max_hourly_usd: float
    max_total_usd: float
    max_active_instances: int
    max_disk_gb: int
    max_ttl_minutes: int
    database_path: Path
    watchdog_interval_seconds: int

    @classmethod
    def from_env(cls) -> Settings:
        settings = cls(
            vast_api_key=os.getenv("VAST_API_KEY"),
            manager_token=os.getenv("MENTAT_COMPUTE_TOKEN"),
            max_hourly_usd=_read_float("MENTAT_MAX_HOURLY_USD", 0.50),
            max_total_usd=_read_float("MENTAT_MAX_TOTAL_USD", 1.00),
            max_active_instances=_read_int("MENTAT_MAX_ACTIVE_INSTANCES", 1),
            max_disk_gb=_read_int("MENTAT_MAX_DISK_GB", 80),
            max_ttl_minutes=_read_int("MENTAT_MAX_TTL_MINUTES", 30),
            database_path=Path(
                os.getenv("MENTAT_DATABASE_PATH", "./data/mentat-compute.sqlite3")
            ),
            watchdog_interval_seconds=_read_int("MENTAT_WATCHDOG_SECONDS", 30),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.max_hourly_usd <= 0:
            raise RuntimeError("MENTAT_MAX_HOURLY_USD must be greater than zero")
        if self.max_total_usd <= 0:
            raise RuntimeError("MENTAT_MAX_TOTAL_USD must be greater than zero")
        if self.max_active_instances < 1:
            raise RuntimeError("MENTAT_MAX_ACTIVE_INSTANCES must be at least one")
        if self.max_disk_gb < 20:
            raise RuntimeError("MENTAT_MAX_DISK_GB must be at least 20")
        if self.max_ttl_minutes < 1:
            raise RuntimeError("MENTAT_MAX_TTL_MINUTES must be at least one")
        if self.watchdog_interval_seconds < 10:
            raise RuntimeError("MENTAT_WATCHDOG_SECONDS must be at least 10")
