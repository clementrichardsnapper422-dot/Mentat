"""Durable compare-and-swap paid-execution state machine."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .contracts import (
    BackendKind,
    ExecutionState,
    ProviderLifecycle,
    ProviderResource,
    utc_now,
)


class ExecutionError(RuntimeError):
    pass


TERMINAL_STATES = {
    ExecutionState.REJECTED,
    ExecutionState.EXPIRED,
    ExecutionState.COMPLETED,
    ExecutionState.DESTROYED,
    ExecutionState.CANCELLED,
    ExecutionState.FAILED,
}

LEGAL_TRANSITIONS: dict[ExecutionState, frozenset[ExecutionState]] = {
    ExecutionState.CREATED: frozenset({ExecutionState.PLANNED, ExecutionState.CANCELLED}),
    ExecutionState.PLANNED: frozenset(
        {ExecutionState.AWAITING_APPROVAL, ExecutionState.CANCELLED, ExecutionState.FAILED}
    ),
    ExecutionState.AWAITING_APPROVAL: frozenset(
        {
            ExecutionState.APPROVED,
            ExecutionState.REJECTED,
            ExecutionState.EXPIRED,
            ExecutionState.CANCELLED,
        }
    ),
    ExecutionState.APPROVED: frozenset(
        {ExecutionState.RESERVING, ExecutionState.EXPIRED, ExecutionState.CANCELLED}
    ),
    ExecutionState.RESERVING: frozenset(
        {ExecutionState.ACQUIRING, ExecutionState.FAILED, ExecutionState.CANCELLED}
    ),
    ExecutionState.ACQUIRING: frozenset(
        {
            ExecutionState.AMBIGUOUS,
            ExecutionState.WARMING,
            ExecutionState.READY,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
        }
    ),
    ExecutionState.AMBIGUOUS: frozenset({ExecutionState.RECONCILING, ExecutionState.FAILED}),
    ExecutionState.RECONCILING: frozenset(
        {
            ExecutionState.ACQUIRING,
            ExecutionState.WARMING,
            ExecutionState.READY,
            ExecutionState.COOLING,
            ExecutionState.DESTROYING,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.WARMING: frozenset(
        {
            ExecutionState.READY,
            ExecutionState.AMBIGUOUS,
            ExecutionState.COOLING,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.READY: frozenset(
        {ExecutionState.RUNNING, ExecutionState.COOLING, ExecutionState.DESTROYING}
    ),
    ExecutionState.RUNNING: frozenset(
        {
            ExecutionState.VERIFYING,
            ExecutionState.COMPLETED,
            ExecutionState.COOLING,
            ExecutionState.AMBIGUOUS,
            ExecutionState.FAILED,
        }
    ),
    ExecutionState.VERIFYING: frozenset(
        {ExecutionState.COMPLETED, ExecutionState.COOLING, ExecutionState.FAILED}
    ),
    ExecutionState.COMPLETED: frozenset({ExecutionState.COOLING, ExecutionState.DESTROYING}),
    ExecutionState.COOLING: frozenset(
        {ExecutionState.COOLED, ExecutionState.AMBIGUOUS, ExecutionState.FAILED}
    ),
    ExecutionState.COOLED: frozenset(
        {ExecutionState.WARMING, ExecutionState.DESTROYING, ExecutionState.DESTROYED}
    ),
    ExecutionState.DESTROYING: frozenset(
        {ExecutionState.DESTROYED, ExecutionState.AMBIGUOUS, ExecutionState.FAILED}
    ),
    ExecutionState.REJECTED: frozenset(),
    ExecutionState.EXPIRED: frozenset(),
    ExecutionState.DESTROYED: frozenset(),
    ExecutionState.CANCELLED: frozenset(),
    ExecutionState.FAILED: frozenset({ExecutionState.RECONCILING}),
}


@dataclass(frozen=True)
class ExecutionRecord:
    execution_id: str
    decision_id: str
    model_id: str
    backend: BackendKind
    state: ExecutionState
    provider_lifecycle: ProviderLifecycle
    version: int
    created_at: str
    updated_at: str
    approval_lease_id: str | None = None
    spend_reservation_id: str | None = None
    provider_resource_id: str | None = None
    provider_endpoint_url: str | None = None
    hourly_usd: float | None = None
    estimated_total_usd: float | None = None
    actual_total_usd: float | None = None
    attempt: int = 0
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["backend"] = self.backend.value
        value["state"] = self.state.value
        value["provider_lifecycle"] = self.provider_lifecycle.value
        return value


class ExecutionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS executions(
                    execution_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    state TEXT NOT NULL,
                    provider_lifecycle TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approval_lease_id TEXT,
                    spend_reservation_id TEXT,
                    provider_resource_id TEXT,
                    provider_endpoint_url TEXT,
                    hourly_usd REAL,
                    estimated_total_usd REAL,
                    actual_total_usd REAL,
                    attempt INTEGER NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    metadata_json TEXT NOT NULL,
                    UNIQUE(backend, provider_resource_id)
                );
                CREATE INDEX IF NOT EXISTS idx_executions_state
                    ON executions(state, updated_at DESC);
                CREATE TABLE IF NOT EXISTS execution_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    detail_json TEXT NOT NULL,
                    FOREIGN KEY(execution_id) REFERENCES executions(execution_id)
                );
                """
            )

    def create(
        self,
        *,
        execution_id: str,
        decision_id: str,
        model_id: str,
        backend: BackendKind,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionRecord:
        timestamp = utc_now()
        with self._lock, self._connection:
            try:
                self._connection.execute(
                    """
                    INSERT INTO executions(
                        execution_id,decision_id,model_id,backend,state,provider_lifecycle,
                        version,created_at,updated_at,attempt,metadata_json
                    ) VALUES(?,?,?,?,?,?,0,?,?,0,?)
                    """,
                    (
                        execution_id,
                        decision_id,
                        model_id,
                        backend.value,
                        ExecutionState.CREATED.value,
                        ProviderLifecycle.ABSENT.value,
                        timestamp,
                        timestamp,
                        json.dumps(metadata or {}, sort_keys=True),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ExecutionError("execution already exists") from exc
            self._event(
                execution_id,
                None,
                ExecutionState.CREATED,
                "created",
                "system",
                metadata or {},
            )
        return self._required(execution_id)

    def get(self, execution_id: str) -> ExecutionRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM executions WHERE execution_id=?", (execution_id,)
            ).fetchone()
        return self._row(row) if row else None

    def list(
        self,
        *,
        state: ExecutionState | None = None,
        limit: int = 100,
    ) -> list[ExecutionRecord]:
        with self._lock:
            if state is None:
                rows = self._connection.execute(
                    "SELECT * FROM executions ORDER BY updated_at DESC LIMIT ?",
                    (max(1, min(limit, 500)),),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    "SELECT * FROM executions WHERE state=? ORDER BY updated_at DESC LIMIT ?",
                    (state.value, max(1, min(limit, 500))),
                ).fetchall()
        return [self._row(row) for row in rows]

    def transition(
        self,
        execution_id: str,
        target: ExecutionState,
        *,
        actor: str,
        expected_version: int | None = None,
        provider_lifecycle: ProviderLifecycle | None = None,
        detail: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        actual_total_usd: float | None = None,
    ) -> ExecutionRecord:
        if not actor.strip():
            raise ValueError("transition actor is required")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                current = self._required_row(execution_id)
                source = ExecutionState(current["state"])
                if expected_version is not None and int(current["version"]) != expected_version:
                    raise ExecutionError("execution version changed")
                if target not in LEGAL_TRANSITIONS[source]:
                    raise ExecutionError(
                        f"illegal execution transition: {source.value} -> {target.value}"
                    )
                next_version = int(current["version"]) + 1
                lifecycle = provider_lifecycle or ProviderLifecycle(current["provider_lifecycle"])
                result = self._connection.execute(
                    """
                    UPDATE executions SET
                        state=?,provider_lifecycle=?,version=?,updated_at=?,
                        error_code=?,error_message=?,
                        actual_total_usd=COALESCE(?,actual_total_usd)
                    WHERE execution_id=? AND version=?
                    """,
                    (
                        target.value,
                        lifecycle.value,
                        next_version,
                        utc_now(),
                        error_code,
                        error_message,
                        actual_total_usd,
                        execution_id,
                        int(current["version"]),
                    ),
                )
                if result.rowcount != 1:
                    raise ExecutionError("execution version changed")
                self._event(execution_id, source, target, "transition", actor, detail or {})
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
        return self._required(execution_id)

    def bind_authority(
        self,
        execution_id: str,
        *,
        lease_id: str,
        reservation_id: str,
        hourly_usd: float,
        estimated_total_usd: float,
        actor: str,
        expected_version: int | None = None,
    ) -> ExecutionRecord:
        if min(hourly_usd, estimated_total_usd) < 0:
            raise ValueError("execution spend values cannot be negative")
        return self._update_fields(
            execution_id,
            actor=actor,
            expected_version=expected_version,
            approval_lease_id=lease_id,
            spend_reservation_id=reservation_id,
            hourly_usd=hourly_usd,
            estimated_total_usd=estimated_total_usd,
            event_type="authority_bound",
        )

    def attach_resource(
        self,
        execution_id: str,
        resource: ProviderResource,
        *,
        actor: str,
        expected_version: int | None = None,
    ) -> ExecutionRecord:
        with self._lock:
            owner = self._connection.execute(
                """
                SELECT execution_id FROM executions
                WHERE backend=? AND provider_resource_id=? AND execution_id<>?
                """,
                (resource.backend.value, resource.resource_id, execution_id),
            ).fetchone()
        if owner:
            raise ExecutionError(
                f"provider resource is already owned by execution {owner['execution_id']}"
            )
        try:
            return self._update_fields(
                execution_id,
                actor=actor,
                expected_version=expected_version,
                provider_resource_id=resource.resource_id,
                provider_endpoint_url=resource.endpoint_url,
                provider_lifecycle=resource.lifecycle.value,
                hourly_usd=resource.hourly_usd,
                event_type="provider_resource_attached",
            )
        except sqlite3.IntegrityError as exc:
            raise ExecutionError("provider resource is already owned") from exc

    def increment_attempt(
        self,
        execution_id: str,
        *,
        actor: str,
        expected_version: int | None = None,
    ) -> ExecutionRecord:
        return self._update_fields(
            execution_id,
            actor=actor,
            expected_version=expected_version,
            increment_attempt=True,
            event_type="attempt_incremented",
        )

    def events(self, execution_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM execution_events WHERE execution_id=? ORDER BY id ASC",
                (execution_id,),
            ).fetchall()
        return [{**dict(row), "detail": json.loads(row["detail_json"] or "{}")} for row in rows]

    def startup_recovery_plan(self) -> list[dict[str, Any]]:
        plan: list[dict[str, Any]] = []
        for record in self.list(limit=500):
            if record.state in TERMINAL_STATES or record.state == ExecutionState.COOLED:
                continue
            if record.provider_resource_id:
                action = "observe_then_cool_or_reconcile"
            elif record.state in {ExecutionState.ACQUIRING, ExecutionState.AMBIGUOUS}:
                action = "reconcile_create_before_any_retry"
            elif record.spend_reservation_id:
                action = "release_or_reconcile_reserved_exposure"
            else:
                action = "fail_closed_without_paid_mutation"
            plan.append(
                {
                    "execution_id": record.execution_id,
                    "state": record.state.value,
                    "provider_lifecycle": record.provider_lifecycle.value,
                    "resource_id": record.provider_resource_id,
                    "reservation_id": record.spend_reservation_id,
                    "action": action,
                    "new_paid_mutation_allowed": False,
                }
            )
        return plan

    def _update_fields(
        self,
        execution_id: str,
        *,
        actor: str,
        expected_version: int | None,
        event_type: str,
        increment_attempt: bool = False,
        **fields: Any,
    ) -> ExecutionRecord:
        allowed = {
            "approval_lease_id",
            "spend_reservation_id",
            "provider_resource_id",
            "provider_endpoint_url",
            "provider_lifecycle",
            "hourly_usd",
            "estimated_total_usd",
            "actual_total_usd",
            "error_code",
            "error_message",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unsupported execution fields: {sorted(unknown)}")
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                current = self._required_row(execution_id)
                version = int(current["version"])
                if expected_version is not None and version != expected_version:
                    raise ExecutionError("execution version changed")
                assignments = [f"{name}=?" for name in fields]
                values = list(fields.values())
                if increment_attempt:
                    assignments.append("attempt=attempt+1")
                assignments.extend(["version=version+1", "updated_at=?"])
                values.append(utc_now())
                values.extend([execution_id, version])
                result = self._connection.execute(
                    f"UPDATE executions SET {','.join(assignments)} "
                    "WHERE execution_id=? AND version=?",
                    values,
                )
                if result.rowcount != 1:
                    raise ExecutionError("execution version changed")
                state = ExecutionState(current["state"])
                self._event(execution_id, state, state, event_type, actor, fields)
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
        return self._required(execution_id)

    def _required(self, execution_id: str) -> ExecutionRecord:
        record = self.get(execution_id)
        if record is None:
            raise KeyError("execution not found")
        return record

    def _required_row(self, execution_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM executions WHERE execution_id=?", (execution_id,)
        ).fetchone()
        if not row:
            raise KeyError("execution not found")
        return row

    def _event(
        self,
        execution_id: str,
        source: ExecutionState | None,
        target: ExecutionState,
        event_type: str,
        actor: str,
        detail: dict[str, Any],
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO execution_events(
                execution_id,created_at,from_state,to_state,event_type,actor,detail_json
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                execution_id,
                utc_now(),
                source.value if source else None,
                target.value,
                event_type,
                actor,
                json.dumps(detail, sort_keys=True, default=str),
            ),
        )

    @staticmethod
    def _row(row: sqlite3.Row) -> ExecutionRecord:
        return ExecutionRecord(
            execution_id=row["execution_id"],
            decision_id=row["decision_id"],
            model_id=row["model_id"],
            backend=BackendKind(row["backend"]),
            state=ExecutionState(row["state"]),
            provider_lifecycle=ProviderLifecycle(row["provider_lifecycle"]),
            version=int(row["version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approval_lease_id=row["approval_lease_id"],
            spend_reservation_id=row["spend_reservation_id"],
            provider_resource_id=row["provider_resource_id"],
            provider_endpoint_url=row["provider_endpoint_url"],
            hourly_usd=float(row["hourly_usd"]) if row["hourly_usd"] is not None else None,
            estimated_total_usd=(
                float(row["estimated_total_usd"])
                if row["estimated_total_usd"] is not None
                else None
            ),
            actual_total_usd=(
                float(row["actual_total_usd"]) if row["actual_total_usd"] is not None else None
            ),
            attempt=int(row["attempt"]),
            error_code=row["error_code"],
            error_message=row["error_message"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
