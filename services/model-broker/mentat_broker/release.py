"""Evidence-backed Mentat 1.0 release gates.

A release gate passes only when retained evidence is recorded. Engineering,
owner-machine, external-provider, and signing evidence remain distinguishable;
code existing by itself can never manufacture a production-ready claim.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .contracts import utc_now

EvidenceKind = Literal["automated", "owner", "external", "signing", "security"]
EvidenceStatus = Literal["pending", "passed", "failed", "accepted_risk", "not_applicable"]


@dataclass(frozen=True)
class ReleaseRequirement:
    requirement_id: str
    gate: int
    title: str
    kind: EvidenceKind
    required: bool = True


@dataclass(frozen=True)
class ReleaseEvidence:
    requirement_id: str
    status: EvidenceStatus
    observed_at: str
    source: str
    artifact: str | None = None
    sha256: str | None = None
    notes: str | None = None
    actor: str = "system"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


REQUIREMENTS: tuple[ReleaseRequirement, ...] = (
    ReleaseRequirement(
        "G0_PRIVATE_REPOSITORY",
        0,
        "Repository is private and detached from public fork network",
        "owner",
    ),
    ReleaseRequirement(
        "G0_PROTECTED_MAIN", 0, "Protected main and focused required checks enabled", "owner"
    ),
    ReleaseRequirement(
        "G0_REPRODUCIBLE_BUILD",
        0,
        "Installer build is reproducible from pinned dependencies",
        "automated",
    ),
    ReleaseRequirement(
        "G0_SBOM_PROVENANCE", 0, "SBOM, checksums, and provenance are retained", "automated"
    ),
    ReleaseRequirement(
        "G0_SIGNED_INSTALLER", 0, "Windows installer is Authenticode signed and verified", "signing"
    ),
    ReleaseRequirement(
        "G1_CLEAN_WINDOWS_INSTALL",
        1,
        "Clean Windows installation succeeds without source checkout",
        "owner",
    ),
    ReleaseRequirement("G1_DOCTOR_GREEN", 1, "Installed mentat doctor is green", "owner"),
    ReleaseRequirement(
        "G1_DOCKER_TOOL_ISOLATION",
        1,
        "Actual OpenClaw tool execution is isolated in Docker",
        "owner",
    ),
    ReleaseRequirement(
        "G1_CREDENTIAL_BOUNDARY",
        1,
        "Gateway, renderer, tools, prompts, URLs, and logs cannot access spending credentials",
        "owner",
    ),
    ReleaseRequirement(
        "G1_AUTH_BOUNDARY",
        1,
        "Broker client/admin authentication is proven end to end",
        "automated",
    ),
    ReleaseRequirement(
        "G1_FAKE_FULL_LOOP",
        1,
        "Fake Vast and fake inference complete chat and tool loops",
        "automated",
    ),
    ReleaseRequirement(
        "G1_FAILURE_RECOVERY",
        1,
        "Reject, timeout, malformed, shutdown, process-kill, logoff, and reboot recovery pass",
        "owner",
    ),
    ReleaseRequirement(
        "G2_VAST_PERMISSION_MATRIX",
        2,
        "Vast API assumptions and least-privilege permission matrix are live validated",
        "external",
    ),
    ReleaseRequirement(
        "G2_LOW_COST_CANARY",
        2,
        "Capped low-cost Vast canary passes approval, reuse, rejection, cooling, and crash recovery",
        "external",
    ),
    ReleaseRequirement(
        "G2_BILLING_RECONCILIATION",
        2,
        "Actual Vast bill is imported and reconciled to displayed ceilings",
        "external",
    ),
    ReleaseRequirement(
        "G3_KIMI_CANARY",
        3,
        "Official Kimi profile passes startup, tools, reasoning, context, and streaming",
        "external",
    ),
    ReleaseRequirement(
        "G3_CAP_ENFORCEMENT", 3, "Kimi four-hour and total-dollar caps are proven", "external"
    ),
    ReleaseRequirement(
        "G4_SOAK", 4, "100-session, 24-hour, and multi-day soak completes without leaks", "external"
    ),
    ReleaseRequirement(
        "G4_ADVERSARIAL_RECOVERY",
        4,
        "Network, disk, SQLite, concurrency, restart, and rollback failures are safe",
        "owner",
    ),
    ReleaseRequirement(
        "G5_SECURITY_REVIEW",
        5,
        "Threat model review findings are closed or explicitly accepted",
        "security",
    ),
    ReleaseRequirement(
        "G5_RUNBOOKS",
        5,
        "Operator, incident, backup, and recovery runbooks are complete",
        "automated",
    ),
    ReleaseRequirement(
        "G5_RELEASE_ARTIFACT",
        5,
        "Versioned signed release artifact is installed and verified",
        "signing",
    ),
)


class ReleaseEvidenceStore:
    SCHEMA_VERSION = 1

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.path.exists():
            self._write(
                {"schema_version": self.SCHEMA_VERSION, "updated_at": utc_now(), "evidence": {}}
            )
        else:
            self._read()

    def _read(self) -> dict[str, Any]:
        with self._lock:
            try:
                value = json.loads(self.path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"release evidence is unreadable: {exc}") from exc
            if value.get("schema_version") != self.SCHEMA_VERSION:
                raise RuntimeError("unsupported release evidence schema")
            if not isinstance(value.get("evidence"), dict):
                raise RuntimeError("release evidence object is malformed")
            return value

    def _write(self, value: dict[str, Any]) -> None:
        with self._lock:
            value["updated_at"] = utc_now()
            handle, temp_name = tempfile.mkstemp(
                prefix=self.path.name + ".",
                suffix=".tmp",
                dir=self.path.parent,
            )
            try:
                with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                    json.dump(value, stream, indent=2, sort_keys=True)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, self.path)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)

    def record(self, evidence: ReleaseEvidence) -> None:
        known = {item.requirement_id for item in REQUIREMENTS}
        if evidence.requirement_id not in known:
            raise KeyError(f"unknown release requirement: {evidence.requirement_id}")
        if evidence.status == "passed" and not evidence.source.strip():
            raise ValueError("passing evidence requires a source")
        if evidence.status == "accepted_risk" and not evidence.notes:
            raise ValueError("accepted risk requires notes")
        with self._lock:
            value = self._read()
            history = value["evidence"].setdefault(evidence.requirement_id, [])
            history.append(evidence.as_dict())
            self._write(value)

    def latest(self, requirement_id: str) -> ReleaseEvidence | None:
        value = self._read()
        history = value["evidence"].get(requirement_id, [])
        return ReleaseEvidence(**history[-1]) if history else None

    def all_latest(self) -> dict[str, ReleaseEvidence]:
        value = self._read()
        return {
            key: ReleaseEvidence(**history[-1])
            for key, history in value["evidence"].items()
            if history
        }

    def report(self) -> dict[str, Any]:
        latest = self.all_latest()
        gates: dict[int, dict[str, Any]] = {}
        for requirement in REQUIREMENTS:
            evidence = latest.get(requirement.requirement_id)
            status: EvidenceStatus = evidence.status if evidence else "pending"
            passed = status in {"passed", "not_applicable"} or (
                status == "accepted_risk" and requirement.kind == "security"
            )
            entry = {
                "requirement_id": requirement.requirement_id,
                "title": requirement.title,
                "kind": requirement.kind,
                "required": requirement.required,
                "status": status,
                "passed": passed,
                "evidence": evidence.as_dict() if evidence else None,
            }
            gate = gates.setdefault(
                requirement.gate, {"gate": requirement.gate, "requirements": []}
            )
            gate["requirements"].append(entry)
        for gate in gates.values():
            gate["passed"] = all(
                item["passed"] for item in gate["requirements"] if item["required"]
            )
        automated_required = [
            item
            for gate in gates.values()
            for item in gate["requirements"]
            if item["required"] and item["kind"] == "automated"
        ]
        return {
            "schema_version": self.SCHEMA_VERSION,
            "product": "Mentat",
            "target_version": "1.0.0",
            "generated_at": utc_now(),
            "engineering_evidence_complete": all(item["passed"] for item in automated_required),
            "production_ready": all(gate["passed"] for gate in gates.values()),
            "release_blocked": not all(gate["passed"] for gate in gates.values()),
            "gates": [gates[index] for index in sorted(gates)],
            "pending": [
                item
                for gate in gates.values()
                for item in gate["requirements"]
                if item["required"] and not item["passed"]
            ],
        }

    def assert_production_ready(self) -> None:
        report = self.report()
        if not report["production_ready"]:
            pending = ", ".join(item["requirement_id"] for item in report["pending"])
            raise RuntimeError(f"Mentat 1.0 release is blocked by retained evidence: {pending}")
