"""Atomic spend authority for Mentat 1.0."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import ApprovalLease, BackendKind, utc_now


@dataclass(frozen=True)
class BudgetPolicy:
    maximum_hourly_usd: float = 32.0
    maximum_session_usd: float = 64.0
    maximum_daily_usd: float = 100.0
    maximum_monthly_usd: float = 500.0
    maximum_retry_usd: float = 10.0
    maximum_fallback_usd: float = 20.0
    maximum_exploration_usd: float = 5.0
    one_paid_session: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SpendReservation:
    reservation_id: str
    decision_id: str
    lease_id: str
    kind: str
    state: str
    reserved_usd: float
    committed_usd: float
    hourly_usd: float
    created_at: str
    expires_at: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class SpendError(RuntimeError):
    pass


class SpendGovernor:
    """The only component allowed to increase paid exposure."""

    ACTIVE_STATES = {"reserved", "reconciling"}

    def __init__(
        self,
        path: Path,
        *,
        signing_secret: bytes,
        policy: BudgetPolicy | None = None,
    ) -> None:
        if len(signing_secret) < 32:
            raise ValueError("spend signing secret must contain at least 32 bytes")
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.signing_secret = signing_secret
        self.policy = policy or BudgetPolicy()
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout=30000")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _migrate(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS spend_settings(
                    key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS spend_reservations(
                    reservation_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    state TEXT NOT NULL,
                    reserved_usd REAL NOT NULL,
                    committed_usd REAL NOT NULL DEFAULT 0,
                    hourly_usd REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(decision_id, lease_id, kind)
                );
                CREATE INDEX IF NOT EXISTS idx_spend_state
                    ON spend_reservations(state, created_at DESC);
                CREATE TABLE IF NOT EXISTS spend_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    reservation_id TEXT,
                    decision_id TEXT,
                    amount_usd REAL NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_spend_events
                    ON spend_events(created_at DESC);
                """
            )
            if self._setting("kill_switch") is None:
                self._set_setting("kill_switch", False)
            if self._setting("policy") is None:
                self._set_setting("policy", self.policy.as_dict())

    def _setting(self, key: str) -> Any:
        row = self._connection.execute(
            "SELECT value_json FROM spend_settings WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row["value_json"]) if row else None

    def _set_setting(self, key: str, value: Any) -> None:
        self._connection.execute(
            """
            INSERT INTO spend_settings(key,value_json,updated_at) VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET
                value_json=excluded.value_json, updated_at=excluded.updated_at
            """,
            (key, json.dumps(value, sort_keys=True), utc_now()),
        )

    def kill_switch_enabled(self) -> bool:
        with self._lock:
            return bool(self._setting("kill_switch"))

    def set_kill_switch(self, enabled: bool, *, reason: str, actor: str) -> None:
        if not reason.strip() or not actor.strip():
            raise ValueError("kill-switch changes require actor and reason")
        with self._lock, self._connection:
            self._set_setting("kill_switch", bool(enabled))
            self._event(
                "kill_switch_enabled" if enabled else "kill_switch_disabled",
                0,
                payload={"reason": reason, "actor": actor},
            )

    def issue_lease(
        self,
        *,
        decision_id: str,
        subject: str,
        expires_at: str,
        backend: BackendKind,
        model_id: str,
        maximum_hourly_usd: float,
        maximum_total_usd: float,
        maximum_attempts: int = 1,
        fallback_allowed: bool = False,
    ) -> ApprovalLease:
        if self.kill_switch_enabled():
            raise SpendError("paid-compute kill switch is enabled")
        if maximum_hourly_usd > self.policy.maximum_hourly_usd:
            raise SpendError("requested hourly ceiling exceeds policy")
        if maximum_total_usd > self.policy.maximum_session_usd:
            raise SpendError("requested session ceiling exceeds policy")
        return ApprovalLease.issue(
            self.signing_secret,
            decision_id=decision_id,
            subject=subject,
            expires_at=expires_at,
            allowed_backend=backend,
            allowed_model_id=model_id,
            maximum_hourly_usd=maximum_hourly_usd,
            maximum_total_usd=maximum_total_usd,
            maximum_attempts=maximum_attempts,
            fallback_allowed=fallback_allowed,
        )

    @staticmethod
    def _prefix(now: datetime, month: bool = False) -> str:
        return now.astimezone(UTC).strftime("%Y-%m" if month else "%Y-%m-%d")

    def _sum_exposure(self, prefix: str) -> float:
        row = self._connection.execute(
            """
            SELECT COALESCE(SUM(CASE
                WHEN state IN ('reserved','reconciling') THEN reserved_usd
                WHEN state='committed' THEN committed_usd ELSE 0 END),0) exposure
            FROM spend_reservations WHERE created_at LIKE ?
            """,
            (prefix + "%",),
        ).fetchone()
        return float(row["exposure"] or 0)

    def _active_count(self) -> int:
        marks = ",".join("?" for _ in self.ACTIVE_STATES)
        row = self._connection.execute(
            f"SELECT COUNT(*) count FROM spend_reservations WHERE state IN ({marks})",
            tuple(sorted(self.ACTIVE_STATES)),
        ).fetchone()
        return int(row["count"] or 0)

    def reserve(
        self,
        lease: ApprovalLease,
        *,
        reservation_id: str,
        subject: str,
        backend: BackendKind,
        model_id: str,
        hourly_usd: float,
        worst_case_usd: float,
        kind: str = "primary",
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> SpendReservation:
        current = now or datetime.now(UTC)
        lease.verify(
            self.signing_secret,
            now=current,
            subject=subject,
            backend=backend,
            model_id=model_id,
        )
        if min(hourly_usd, worst_case_usd) <= 0:
            raise SpendError("hourly and total reservation values must be positive")
        if hourly_usd > min(lease.maximum_hourly_usd, self.policy.maximum_hourly_usd):
            raise SpendError("provider hourly rate exceeds approved ceiling")
        if worst_case_usd > min(lease.maximum_total_usd, self.policy.maximum_session_usd):
            raise SpendError("worst-case exposure exceeds approved session ceiling")
        kind_cap = {
            "retry": self.policy.maximum_retry_usd,
            "fallback": self.policy.maximum_fallback_usd,
            "exploration": self.policy.maximum_exploration_usd,
        }.get(kind)
        if kind_cap is not None and worst_case_usd > kind_cap:
            raise SpendError(f"{kind} exposure exceeds its dedicated policy cap")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                if bool(self._setting("kill_switch")):
                    raise SpendError("paid-compute kill switch is enabled")
                existing = self._connection.execute(
                    "SELECT * FROM spend_reservations WHERE reservation_id=?",
                    (reservation_id,),
                ).fetchone()
                if existing:
                    saved = self._row(existing)
                    if (
                        saved.decision_id != lease.decision_id
                        or saved.lease_id != lease.lease_id
                        or saved.reserved_usd != worst_case_usd
                    ):
                        raise SpendError("reservation id was reused with different authority")
                    self._connection.commit()
                    return saved
                if self.policy.one_paid_session and self._active_count():
                    raise SpendError("another paid session already owns active exposure")
                if self._sum_exposure(self._prefix(current)) + worst_case_usd > self.policy.maximum_daily_usd:
                    raise SpendError("daily spend ceiling would be exceeded")
                if self._sum_exposure(self._prefix(current, True)) + worst_case_usd > self.policy.maximum_monthly_usd:
                    raise SpendError("monthly spend ceiling would be exceeded")
                self._connection.execute(
                    """
                    INSERT INTO spend_reservations(
                        reservation_id,decision_id,lease_id,kind,state,reserved_usd,
                        committed_usd,hourly_usd,created_at,expires_at,metadata_json
                    ) VALUES(?,?,?,?, 'reserved',?,0,?,?,?,?)
                    """,
                    (
                        reservation_id,
                        lease.decision_id,
                        lease.lease_id,
                        kind,
                        worst_case_usd,
                        hourly_usd,
                        current.isoformat(),
                        lease.expires_at,
                        json.dumps(metadata or {}, sort_keys=True),
                    ),
                )
                self._event(
                    "reserved",
                    worst_case_usd,
                    reservation_id,
                    lease.decision_id,
                    {"kind": kind, "hourly_usd": hourly_usd},
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
        return self._required(reservation_id)

    def commit(self, reservation_id: str, actual_usd: float) -> SpendReservation:
        if actual_usd < 0:
            raise ValueError("actual spend cannot be negative")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._require_row(reservation_id)
                if row["state"] == "committed":
                    self._connection.commit()
                    return self._row(row)
                if row["state"] != "reserved":
                    raise SpendError(f"cannot commit a {row['state']} reservation")
                if actual_usd > float(row["reserved_usd"]) + 1e-9:
                    self._set_setting("kill_switch", True)
                    self._connection.execute(
                        "UPDATE spend_reservations SET state='reconciling' WHERE reservation_id=?",
                        (reservation_id,),
                    )
                    self._event(
                        "overspend_detected",
                        actual_usd,
                        reservation_id,
                        row["decision_id"],
                        {"reserved_usd": row["reserved_usd"]},
                    )
                    self._connection.commit()
                    raise SpendError("actual spend exceeded the reserved exposure; kill switch enabled")
                self._connection.execute(
                    "UPDATE spend_reservations SET state='committed',committed_usd=? WHERE reservation_id=?",
                    (actual_usd, reservation_id),
                )
                self._event(
                    "committed",
                    actual_usd,
                    reservation_id,
                    row["decision_id"],
                    {"released_usd": float(row["reserved_usd"]) - actual_usd},
                )
                self._connection.commit()
            except SpendError:
                if self._connection.in_transaction:
                    self._connection.rollback()
                raise
            except Exception:
                self._connection.rollback()
                raise
        return self._required(reservation_id)

    def release(self, reservation_id: str, *, reason: str) -> SpendReservation:
        if not reason.strip():
            raise ValueError("release reason is required")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._require_row(reservation_id)
                if row["state"] == "released":
                    self._connection.commit()
                    return self._row(row)
                if row["state"] not in {"reserved", "reconciling"}:
                    raise SpendError(f"cannot release a {row['state']} reservation")
                self._connection.execute(
                    "UPDATE spend_reservations SET state='released' WHERE reservation_id=?",
                    (reservation_id,),
                )
                self._event(
                    "released",
                    float(row["reserved_usd"]),
                    reservation_id,
                    row["decision_id"],
                    {"reason": reason},
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
        return self._required(reservation_id)

    def reconcile(self, reservation_id: str, actual_usd: float, *, source: str) -> SpendReservation:
        if actual_usd < 0 or not source.strip():
            raise ValueError("reconciliation requires non-negative actual spend and a source")
        with self._lock, self._connection:
            row = self._require_row(reservation_id)
            state = "committed" if actual_usd > 0 else "released"
            self._connection.execute(
                "UPDATE spend_reservations SET state=?,committed_usd=? WHERE reservation_id=?",
                (state, actual_usd, reservation_id),
            )
            if actual_usd > float(row["reserved_usd"]) + 1e-9:
                self._set_setting("kill_switch", True)
            self._event(
                "reconciled",
                actual_usd,
                reservation_id,
                row["decision_id"],
                {"source": source, "reserved_usd": row["reserved_usd"]},
            )
        return self._required(reservation_id)

    def recover_expired(self, now: datetime | None = None) -> list[str]:
        current = (now or datetime.now(UTC)).isoformat()
        released: list[str] = []
        with self._lock, self._connection:
            rows = self._connection.execute(
                "SELECT * FROM spend_reservations WHERE state='reserved' AND expires_at<=?",
                (current,),
            ).fetchall()
            for row in rows:
                self._connection.execute(
                    "UPDATE spend_reservations SET state='released' WHERE reservation_id=?",
                    (row["reservation_id"],),
                )
                self._event(
                    "expired_released",
                    float(row["reserved_usd"]),
                    row["reservation_id"],
                    row["decision_id"],
                    {},
                )
                released.append(row["reservation_id"])
        return released

    def get(self, reservation_id: str) -> SpendReservation | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM spend_reservations WHERE reservation_id=?",
                (reservation_id,),
            ).fetchone()
        return self._row(row) if row else None

    def list_reservations(self, limit: int = 100) -> list[SpendReservation]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM spend_reservations ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [self._row(row) for row in rows]

    def snapshot(self, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(UTC)
        with self._lock:
            active = self._connection.execute(
                "SELECT COALESCE(SUM(reserved_usd),0) total FROM spend_reservations WHERE state IN ('reserved','reconciling')"
            ).fetchone()
            committed = self._connection.execute(
                "SELECT COALESCE(SUM(committed_usd),0) total FROM spend_reservations WHERE state='committed'"
            ).fetchone()
            events = self._connection.execute(
                "SELECT * FROM spend_events ORDER BY id DESC LIMIT 20"
            ).fetchall()
            return {
                "kill_switch": bool(self._setting("kill_switch")),
                "policy": self.policy.as_dict(),
                "active_reserved_usd": float(active["total"] or 0),
                "committed_usd": float(committed["total"] or 0),
                "today_exposure_usd": self._sum_exposure(self._prefix(current)),
                "month_exposure_usd": self._sum_exposure(self._prefix(current, True)),
                "active_sessions": self._active_count(),
                "recent_events": [
                    {**dict(row), "payload": json.loads(row["payload_json"])} for row in events
                ],
            }

    def _required(self, reservation_id: str) -> SpendReservation:
        value = self.get(reservation_id)
        if value is None:
            raise SpendError("reservation disappeared")
        return value

    def _require_row(self, reservation_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM spend_reservations WHERE reservation_id=?", (reservation_id,)
        ).fetchone()
        if not row:
            raise KeyError("spend reservation not found")
        return row

    @staticmethod
    def _row(row: sqlite3.Row) -> SpendReservation:
        return SpendReservation(
            reservation_id=row["reservation_id"],
            decision_id=row["decision_id"],
            lease_id=row["lease_id"],
            kind=row["kind"],
            state=row["state"],
            reserved_usd=float(row["reserved_usd"]),
            committed_usd=float(row["committed_usd"]),
            hourly_usd=float(row["hourly_usd"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def _event(
        self,
        event_type: str,
        amount_usd: float,
        reservation_id: str | None = None,
        decision_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO spend_events(
                created_at,event_type,reservation_id,decision_id,amount_usd,payload_json
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                utc_now(),
                event_type,
                reservation_id,
                decision_id,
                amount_usd,
                json.dumps(payload or {}, sort_keys=True),
            ),
        )
