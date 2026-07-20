from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import BenchmarkRecord, Decision, Offer


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class BrokerStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _migrate(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;

                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    prompt_preview TEXT NOT NULL,
                    prompt_digest TEXT NOT NULL,
                    task_class TEXT NOT NULL,
                    selected_model TEXT NOT NULL,
                    selected_model_id TEXT NOT NULL,
                    fallback_chain_json TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    quality_score REAL NOT NULL,
                    quality_source TEXT NOT NULL,
                    benchmark_samples INTEGER NOT NULL,
                    offer_json TEXT,
                    offer_source TEXT NOT NULL,
                    estimated_minutes INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL,
                    max_hourly_usd REAL NOT NULL,
                    max_total_usd REAL NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    approved_at TEXT,
                    completed_at TEXT,
                    metadata_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_decisions_created_at
                    ON decisions(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_decisions_status
                    ON decisions(status, created_at DESC);

                CREATE TABLE IF NOT EXISTS benchmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    task_class TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    tokens_per_second REAL,
                    hourly_usd REAL,
                    total_cost_usd REAL,
                    quality_score REAL,
                    notes TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_benchmarks_model_task
                    ON benchmarks(model_id, task_class, created_at DESC);

                CREATE TABLE IF NOT EXISTS sessions (
                    model_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    endpoint_url TEXT,
                    hourly_usd REAL,
                    offer_json TEXT,
                    decision_id TEXT,
                    started_at TEXT,
                    last_used_at TEXT,
                    approved_until TEXT,
                    error TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def save_decision(self, decision: Decision) -> None:
        payload = decision.as_dict()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO decisions (
                    id, created_at, prompt_preview, prompt_digest, task_class,
                    selected_model, selected_model_id, fallback_chain_json,
                    reasons_json, quality_score, quality_source, benchmark_samples,
                    offer_json, offer_source, estimated_minutes, estimated_cost_usd,
                    max_hourly_usd, max_total_usd, status, error, approved_at,
                    completed_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    selected_model=excluded.selected_model,
                    selected_model_id=excluded.selected_model_id,
                    fallback_chain_json=excluded.fallback_chain_json,
                    reasons_json=excluded.reasons_json,
                    quality_score=excluded.quality_score,
                    quality_source=excluded.quality_source,
                    benchmark_samples=excluded.benchmark_samples,
                    offer_json=excluded.offer_json,
                    offer_source=excluded.offer_source,
                    estimated_minutes=excluded.estimated_minutes,
                    estimated_cost_usd=excluded.estimated_cost_usd,
                    max_hourly_usd=excluded.max_hourly_usd,
                    max_total_usd=excluded.max_total_usd,
                    status=excluded.status,
                    error=excluded.error,
                    approved_at=excluded.approved_at,
                    completed_at=excluded.completed_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    decision.id,
                    decision.created_at,
                    decision.prompt_preview,
                    decision.prompt_digest,
                    decision.task_class,
                    decision.selected_model,
                    decision.selected_model_id,
                    json.dumps(decision.fallback_chain),
                    json.dumps(decision.reasons),
                    decision.quality_score,
                    decision.quality_source,
                    decision.benchmark_samples,
                    json.dumps(payload["offer"]) if payload["offer"] else None,
                    decision.offer_source,
                    decision.estimated_minutes,
                    decision.estimated_cost_usd,
                    decision.max_hourly_usd,
                    decision.max_total_usd,
                    decision.status,
                    decision.error,
                    decision.approved_at,
                    decision.completed_at,
                    json.dumps(decision.metadata),
                ),
            )

    def _row_to_decision(self, row: sqlite3.Row) -> Decision:
        raw_offer = json.loads(row["offer_json"]) if row["offer_json"] else None
        offer = Offer(**raw_offer) if raw_offer else None
        return Decision(
            id=row["id"],
            created_at=row["created_at"],
            prompt_preview=row["prompt_preview"],
            prompt_digest=row["prompt_digest"],
            task_class=row["task_class"],
            selected_model=row["selected_model"],
            selected_model_id=row["selected_model_id"],
            fallback_chain=json.loads(row["fallback_chain_json"]),
            reasons=json.loads(row["reasons_json"]),
            quality_score=float(row["quality_score"]),
            quality_source=row["quality_source"],
            benchmark_samples=int(row["benchmark_samples"]),
            offer=offer,
            offer_source=row["offer_source"],
            estimated_minutes=int(row["estimated_minutes"]),
            estimated_cost_usd=float(row["estimated_cost_usd"]),
            max_hourly_usd=float(row["max_hourly_usd"]),
            max_total_usd=float(row["max_total_usd"]),
            status=row["status"],
            error=row["error"],
            approved_at=row["approved_at"],
            completed_at=row["completed_at"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def get_decision(self, decision_id: str) -> Decision | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM decisions WHERE id = ?", (decision_id,)
            ).fetchone()
        return self._row_to_decision(row) if row else None

    def list_decisions(self, *, status: str | None = None, limit: int = 50) -> list[Decision]:
        limit = max(1, min(limit, 200))
        with self._lock:
            if status:
                rows = self._connection.execute(
                    "SELECT * FROM decisions WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [self._row_to_decision(row) for row in rows]

    def update_decision_status(
        self,
        decision_id: str,
        status: str,
        *,
        error: str | None = None,
        approved_at: str | None = None,
        completed_at: str | None = None,
    ) -> Decision | None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE decisions SET status = ?, error = ?,
                    approved_at = COALESCE(?, approved_at),
                    completed_at = COALESCE(?, completed_at)
                WHERE id = ?
                """,
                (status, error, approved_at, completed_at, decision_id),
            )
        return self.get_decision(decision_id)

    def add_benchmark(self, record: BenchmarkRecord) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO benchmarks (
                    created_at, model_id, task_class, success, latency_ms,
                    tokens_per_second, hourly_usd, total_cost_usd, quality_score, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now(),
                    record.model_id,
                    record.task_class,
                    1 if record.success else 0,
                    record.latency_ms,
                    record.tokens_per_second,
                    record.hourly_usd,
                    record.total_cost_usd,
                    record.quality_score,
                    record.notes,
                ),
            )
            return int(cursor.lastrowid)

    def benchmark_summary(self, model_id: str, task_class: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT
                    COUNT(*) AS samples,
                    AVG(CASE WHEN success = 1 THEN 1.0 ELSE 0.0 END) AS success_rate,
                    AVG(latency_ms) AS latency_ms,
                    AVG(tokens_per_second) AS tokens_per_second,
                    AVG(hourly_usd) AS hourly_usd,
                    AVG(total_cost_usd) AS total_cost_usd,
                    AVG(quality_score) AS quality_score
                FROM benchmarks
                WHERE model_id = ? AND task_class = ?
                """,
                (model_id, task_class),
            ).fetchone()
        return {
            "samples": int(row["samples"] or 0),
            "success_rate": float(row["success_rate"] or 0),
            "latency_ms": float(row["latency_ms"]) if row["latency_ms"] is not None else None,
            "tokens_per_second": (
                float(row["tokens_per_second"]) if row["tokens_per_second"] is not None else None
            ),
            "hourly_usd": float(row["hourly_usd"]) if row["hourly_usd"] is not None else None,
            "total_cost_usd": (
                float(row["total_cost_usd"]) if row["total_cost_usd"] is not None else None
            ),
            "quality_score": (
                float(row["quality_score"]) if row["quality_score"] is not None else None
            ),
        }

    def list_benchmarks(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM benchmarks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_session(
        self,
        model_id: str,
        *,
        status: str,
        endpoint_url: str | None = None,
        hourly_usd: float | None = None,
        offer: Offer | None = None,
        decision_id: str | None = None,
        started_at: str | None = None,
        last_used_at: str | None = None,
        approved_until: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO sessions (
                    model_id, status, endpoint_url, hourly_usd, offer_json, decision_id,
                    started_at, last_used_at, approved_until, error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_id) DO UPDATE SET
                    status=excluded.status,
                    endpoint_url=COALESCE(excluded.endpoint_url, sessions.endpoint_url),
                    hourly_usd=COALESCE(excluded.hourly_usd, sessions.hourly_usd),
                    offer_json=COALESCE(excluded.offer_json, sessions.offer_json),
                    decision_id=COALESCE(excluded.decision_id, sessions.decision_id),
                    started_at=COALESCE(excluded.started_at, sessions.started_at),
                    last_used_at=COALESCE(excluded.last_used_at, sessions.last_used_at),
                    approved_until=COALESCE(excluded.approved_until, sessions.approved_until),
                    error=excluded.error,
                    updated_at=excluded.updated_at
                """,
                (
                    model_id,
                    status,
                    endpoint_url,
                    hourly_usd,
                    json.dumps(offer.as_dict()) if offer else None,
                    decision_id,
                    started_at,
                    last_used_at,
                    approved_until,
                    error,
                    utc_now(),
                ),
            )

    def get_session(self, model_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM sessions WHERE model_id = ?", (model_id,)
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["offer"] = json.loads(result.pop("offer_json")) if result.get("offer_json") else None
        return result

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["offer"] = json.loads(item.pop("offer_json")) if item.get("offer_json") else None
            result.append(item)
        return result
