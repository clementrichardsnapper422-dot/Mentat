from __future__ import annotations

import sqlite3
from contextlib import suppress
from pathlib import Path
from typing import Any

from .runtime_policy import QualityAwareBrokerStore
from .store import utc_now


class ProductionBrokerStore(QualityAwareBrokerStore):
    """Use durable SQLite settings and fail fast on a damaged broker database."""

    def __init__(self, path: Path):
        super().__init__(path)
        with self._lock, self._connection:
            self._connection.execute("PRAGMA busy_timeout=5000")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.execute("PRAGMA wal_autocheckpoint=1000")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS decision_ratings (
                    decision_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    task_class TEXT NOT NULL,
                    quality_score REAL NOT NULL,
                    notes TEXT,
                    FOREIGN KEY(decision_id) REFERENCES decisions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_decision_ratings_model_task
                    ON decision_ratings(model_id, task_class, created_at DESC);
                """
            )
            row = self._connection.execute("PRAGMA quick_check").fetchone()
            if not row or str(row[0]).lower() != "ok":
                raise sqlite3.DatabaseError(f"broker database integrity check failed: {row}")
        with suppress(OSError):
            self.path.chmod(0o600)

    def rate_decision(
        self,
        decision_id: str,
        quality_score: float,
        notes: str | None = None,
    ) -> dict[str, Any]:
        score = float(quality_score)
        if not 0 <= score <= 1:
            raise ValueError("quality_score must be between 0 and 1")
        clean_notes = notes.strip()[:1000] if notes else None
        with self._lock, self._connection:
            row = self._connection.execute(
                """
                SELECT selected_model, task_class, status, offer_json, estimated_cost_usd
                FROM decisions
                WHERE id = ?
                """,
                (decision_id,),
            ).fetchone()
            if not row:
                raise ValueError("decision not found")
            if row["status"] != "completed":
                raise ValueError("only completed decisions can be rated")
            existing = self._connection.execute(
                "SELECT 1 FROM decision_ratings WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
            if existing:
                raise ValueError("this decision already has a quality rating")

            hourly_usd = None
            if row["offer_json"]:
                try:
                    import json

                    hourly_usd = float(json.loads(row["offer_json"])["hourly_usd"])
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    hourly_usd = None
            created_at = utc_now()
            self._connection.execute(
                """
                INSERT INTO decision_ratings (
                    decision_id, created_at, model_id, task_class, quality_score, notes
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    created_at,
                    row["selected_model"],
                    row["task_class"],
                    score,
                    clean_notes,
                ),
            )
            self._connection.execute(
                """
                INSERT INTO benchmarks (
                    created_at, model_id, task_class, success, latency_ms,
                    tokens_per_second, hourly_usd, total_cost_usd, quality_score, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    row["selected_model"],
                    row["task_class"],
                    1,
                    0.0,
                    None,
                    hourly_usd,
                    float(row["estimated_cost_usd"]),
                    score,
                    f"User rating for decision {decision_id}"
                    + (f": {clean_notes}" if clean_notes else ""),
                ),
            )
        return {
            "decision_id": decision_id,
            "model_id": row["selected_model"],
            "task_class": row["task_class"],
            "quality_score": score,
            "notes": clean_notes,
            "created_at": created_at,
        }

    def get_rating(self, decision_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM decision_ratings WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        return dict(row) if row else None
