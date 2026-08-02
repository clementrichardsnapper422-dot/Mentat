#!/usr/bin/env python3
"""Zero-dollar acceptance for the Mentat 1.0 release-critical control plane."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "services" / "model-broker"
if str(SERVICE) not in sys.path:
    sys.path.insert(0, str(SERVICE))

from mentat_broker.backends import BackendError  # noqa: E402
from mentat_broker.contracts import (  # noqa: E402
    BackendKind,
    EvidenceTier,
    ExecutionCandidate,
    ExecutionState,
    ModelProfile,
    RangeEstimate,
)
from mentat_broker.runtime import MentatV1Runtime  # noqa: E402
from mentat_broker.spend import SpendError  # noqa: E402


class AcceptanceFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


def fake_candidate() -> ExecutionCandidate:
    profile = ModelProfile(
        profile_id="fake-model-v1",
        model_id="fake-model",
        model_version="1",
        provider="fake",
        backend=BackendKind.FAKE,
        runtime_revision="acceptance",
        capabilities=frozenset({"text", "tools", "code"}),
        task_classes=frozenset({"simple", "general", "code"}),
        context_tokens=128_000,
        quality_prior=1,
        success_prior=1,
        production_eligible=True,
        maximum_hourly_usd=0,
        minimum_reliability=1,
    )
    return ExecutionCandidate(
        candidate_id="fake-candidate",
        profile=profile,
        market=None,
        quality=RangeEstimate(1, 1, 1, "probability"),
        success_probability=RangeEstimate(1, 1, 1, "probability"),
        total_cost_usd=RangeEstimate(0, 0, 0, "USD"),
        latency_ms=RangeEstimate(1, 1, 1, "milliseconds"),
        evidence_tier=EvidenceTier.LIVE_VALIDATED,
        evidence_samples=100,
        evidence_observed_at=datetime.now(UTC).isoformat(),
        eligible=True,
    )


def run_acceptance() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    started_at = datetime.now(UTC).isoformat()

    def check(name: str, action: Callable[[], Any]) -> Any:
        started = time.monotonic()
        try:
            detail = action()
            rendered_detail = detail.as_dict() if hasattr(detail, "as_dict") else detail
            checks.append(
                {
                    "name": name,
                    "status": "passed",
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "detail": rendered_detail,
                }
            )
            return detail
        except Exception as exc:
            checks.append(
                {
                    "name": name,
                    "status": "failed",
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "error": str(exc),
                }
            )
            raise

    with tempfile.TemporaryDirectory(prefix="mentat-v1-acceptance-") as directory:
        root = Path(directory)
        runtime = MentatV1Runtime(root)
        try:
            requirements = check(
                "structured-task-analysis",
                lambda: runtime.analyze_task(
                    "Fix this repository API bug and add tests",
                    input_tokens=10_000,
                    tool_names=["git", "python"],
                    repository_files=300,
                ),
            )
            require(requirements["task_class"] == "code", "task class mismatch")
            require("tools" in requirements["capabilities"], "tool capability missing")

            expires = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
            lease = check(
                "signed-approval-lease",
                lambda: runtime.spend.issue_lease(
                    decision_id="decision-1",
                    subject="acceptance-admin",
                    expires_at=expires,
                    backend=BackendKind.FAKE,
                    model_id="fake-model",
                    maximum_hourly_usd=0.01,
                    maximum_total_usd=0.01,
                ),
            )
            reservation = check(
                "atomic-worst-case-reservation",
                lambda: runtime.spend.reserve(
                    lease,
                    reservation_id="reservation-1",
                    subject="acceptance-admin",
                    backend=BackendKind.FAKE,
                    model_id="fake-model",
                    hourly_usd=0.001,
                    worst_case_usd=0.001,
                    metadata={"paid_compute_used": False},
                ),
            )

            execution = runtime.executions.create(
                execution_id="execution-1",
                decision_id="decision-1",
                model_id="fake-model",
                backend=BackendKind.FAKE,
            )
            for state in (
                ExecutionState.PLANNED,
                ExecutionState.AWAITING_APPROVAL,
                ExecutionState.APPROVED,
                ExecutionState.RESERVING,
            ):
                execution = runtime.executions.transition(
                    execution.execution_id,
                    state,
                    actor="acceptance",
                    expected_version=execution.version,
                )
            execution = runtime.executions.bind_authority(
                execution.execution_id,
                lease_id=lease.lease_id,
                reservation_id=reservation.reservation_id,
                hourly_usd=0.001,
                estimated_total_usd=0.001,
                actor="acceptance",
                expected_version=execution.version,
            )
            execution = runtime.executions.transition(
                execution.execution_id,
                ExecutionState.ACQUIRING,
                actor="acceptance",
                expected_version=execution.version,
            )
            backend = runtime.backends.get(BackendKind.FAKE)
            resource = check(
                "provider-neutral-backend-acquisition",
                lambda: backend.acquire(
                    fake_candidate(),
                    lease,
                    idempotency_key="execution-1",
                ),
            )
            same = backend.acquire(
                fake_candidate(),
                lease,
                idempotency_key="execution-1",
            )
            require(
                same.resource_id == resource.resource_id,
                "idempotency key created a duplicate",
            )
            execution = runtime.executions.attach_resource(
                execution.execution_id,
                resource,
                actor="acceptance",
                expected_version=execution.version,
            )
            for state in (
                ExecutionState.READY,
                ExecutionState.RUNNING,
                ExecutionState.COMPLETED,
            ):
                execution = runtime.executions.transition(
                    execution.execution_id,
                    state,
                    actor="acceptance",
                    expected_version=execution.version,
                )

            def reject_parallel_exposure():
                second = runtime.spend.issue_lease(
                    decision_id="decision-2",
                    subject="acceptance-admin",
                    expires_at=expires,
                    backend=BackendKind.FAKE,
                    model_id="fake-model",
                    maximum_hourly_usd=0.01,
                    maximum_total_usd=0.01,
                )
                try:
                    runtime.spend.reserve(
                        second,
                        reservation_id="reservation-2",
                        subject="acceptance-admin",
                        backend=BackendKind.FAKE,
                        model_id="fake-model",
                        hourly_usd=0.001,
                        worst_case_usd=0.001,
                    )
                except SpendError as exc:
                    return {"rejected": True, "message": str(exc)}
                raise AcceptanceFailure("parallel paid exposure was not rejected")

            check("one-paid-session-invariant", reject_parallel_exposure)
            check(
                "zero-dollar-billing-reconciliation",
                lambda: runtime.spend.commit(reservation.reservation_id, 0),
            )
            require(
                backend.billing(resource.resource_id)["actual_usd"] == 0,
                "fake bill was nonzero",
            )

            def direct_backend_stop_sign():
                try:
                    runtime.backends.get(BackendKind.VAST_DIRECT)
                except BackendError as exc:
                    return {"blocked": True, "error_code": exc.error.code}
                raise AcceptanceFailure(
                    "experimental direct backend became production eligible"
                )

            check("unvalidated-direct-backend-blocked", direct_backend_stop_sign)

            def emergency_lockout():
                runtime.set_kill_switch(True, reason="acceptance", actor="test")
                require(runtime.spend.kill_switch_enabled(), "kill switch did not engage")
                try:
                    runtime.spend.issue_lease(
                        decision_id="decision-3",
                        subject="acceptance-admin",
                        expires_at=expires,
                        backend=BackendKind.FAKE,
                        model_id="fake-model",
                        maximum_hourly_usd=0.01,
                        maximum_total_usd=0.01,
                    )
                except SpendError:
                    return {"new_spend_blocked": True}
                raise AcceptanceFailure("kill switch allowed a new approval lease")

            check("emergency-paid-compute-lockout", emergency_lockout)

            status = check("release-evidence-gates", runtime.status)
            require(
                status["release"]["production_ready"] is False,
                "live evidence was fabricated",
            )
            require(
                any(
                    item["kind"] == "external"
                    for item in status["release"]["pending"]
                ),
                "external release gates disappeared",
            )
            events = runtime.executions.events("execution-1")
            require(len(events) >= 8, "execution transition evidence is incomplete")
        finally:
            runtime.close()

    rendered = json.dumps(checks, sort_keys=True).encode("utf-8")
    return {
        "schema_version": 1,
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "passed": all(item["status"] == "passed" for item in checks),
        "paid_compute_used": False,
        "evidence_digest": hashlib.sha256(rendered).hexdigest(),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Mentat 1.0 release-candidate acceptance"
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = run_acceptance()
    except Exception as exc:
        report = {
            "schema_version": 1,
            "completed_at": datetime.now(UTC).isoformat(),
            "passed": False,
            "paid_compute_used": False,
            "fatal_error": str(exc),
        }
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
