from __future__ import annotations

import sqlite3
from pathlib import Path

from .runtime_policy import QualityAwareBrokerStore


class ProductionBrokerStore(QualityAwareBrokerStore):
    """Use durable SQLite settings and fail fast on a damaged broker database."""

    def __init__(self, path: Path):
        super().__init__(path)
        with self._lock:
            self._connection.execute("PRAGMA busy_timeout=5000")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.execute("PRAGMA wal_autocheckpoint=1000")
            row = self._connection.execute("PRAGMA quick_check").fetchone()
            if not row or str(row[0]).lower() != "ok":
                raise sqlite3.DatabaseError(f"broker database integrity check failed: {row}")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
