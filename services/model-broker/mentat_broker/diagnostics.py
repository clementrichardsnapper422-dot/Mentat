"""Local diagnostics, backup, and bounded repair for Mentat 1.0."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .contracts import utc_now


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    status: str
    message: str
    repairable: bool = False
    detail: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "passed": self.passed}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DiagnosticsService:
    """Runs local checks without reading or returning credential values."""

    DATABASES = ("spend.sqlite3", "executions.sqlite3")

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir = self.data_dir.parent / "backups"

    def run(self, *, include_docker: bool = True) -> dict[str, Any]:
        checks = [
            self._data_directory_check(),
            self._secret_check(),
            *[self._database_check(name) for name in self.DATABASES],
            self._json_check("release-evidence.json", "release-evidence"),
            self._json_check("desktop-settings.json", "desktop-settings"),
        ]
        if include_docker:
            checks.append(self._docker_check())
        return {
            "schema_version": 1,
            "generated_at": utc_now(),
            "passed": all(check.passed for check in checks),
            "checks": [check.as_dict() for check in checks],
            "repairable_failures": [
                check.name for check in checks if not check.passed and check.repairable
            ],
        }

    def _data_directory_check(self) -> DiagnosticCheck:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(
                prefix="diagnostic-", suffix=".tmp", dir=self.data_dir
            )
            os.close(descriptor)
            os.unlink(name)
        except OSError as exc:
            return DiagnosticCheck(
                "data-directory",
                "failed",
                f"Mentat data directory is not safely writable: {exc}",
            )
        return DiagnosticCheck(
            "data-directory",
            "passed",
            "Mentat data directory is writable.",
            detail={"path": str(self.data_dir)},
        )

    def _secret_check(self) -> DiagnosticCheck:
        path = self.data_dir / "spend-authority.key"
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return DiagnosticCheck(
                "spend-authority-key",
                "failed",
                "Spend authority key is missing.",
            )
        except OSError as exc:
            return DiagnosticCheck(
                "spend-authority-key",
                "failed",
                f"Spend authority key cannot be inspected: {exc}",
            )
        if size != 32:
            return DiagnosticCheck(
                "spend-authority-key",
                "failed",
                "Spend authority key has an invalid size.",
            )
        return DiagnosticCheck(
            "spend-authority-key",
            "passed",
            "Spend authority key exists with the expected size.",
        )

    def _database_check(self, name: str) -> DiagnosticCheck:
        path = self.data_dir / name
        if not path.exists():
            return DiagnosticCheck(
                name,
                "failed",
                f"Required database is missing: {name}",
            )
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
            try:
                result = connection.execute("PRAGMA integrity_check").fetchone()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            return DiagnosticCheck(
                name,
                "failed",
                f"Database integrity check failed: {exc}",
                repairable=True,
            )
        if not result or result[0] != "ok":
            return DiagnosticCheck(
                name,
                "failed",
                f"Database reported integrity errors: {result}",
                repairable=True,
            )
        return DiagnosticCheck(name, "passed", "SQLite integrity check passed.")

    def _json_check(self, name: str, label: str) -> DiagnosticCheck:
        path = self.data_dir / name
        if not path.exists():
            return DiagnosticCheck(
                label,
                "failed",
                f"Required state file is missing: {name}",
            )
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            return DiagnosticCheck(
                label,
                "failed",
                f"State file is unreadable: {exc}",
            )
        if not isinstance(value, dict):
            return DiagnosticCheck(
                label,
                "failed",
                "State file must contain a JSON object.",
            )
        return DiagnosticCheck(label, "passed", "State file is readable.")

    @staticmethod
    def _docker_check() -> DiagnosticCheck:
        command = shutil.which("docker")
        if not command:
            return DiagnosticCheck(
                "docker",
                "failed",
                "Docker command was not found. Docker Desktop is required for tool isolation.",
            )
        try:
            result = subprocess.run(
                [command, "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                check=False,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return DiagnosticCheck(
                "docker",
                "failed",
                f"Docker Desktop did not respond safely: {exc}",
            )
        if result.returncode != 0 or not result.stdout.strip():
            message = (result.stderr or result.stdout or "Docker server unavailable").strip()
            return DiagnosticCheck("docker", "failed", message[-500:])
        return DiagnosticCheck(
            "docker",
            "passed",
            "Docker Desktop server is available.",
            detail={"server_version": result.stdout.strip()},
        )

    def safe_repair(self) -> dict[str, Any]:
        """Checkpoint healthy SQLite files; never invent state over corruption."""

        before = self.run(include_docker=False)
        corrupted = [
            item
            for item in before["checks"]
            if item["name"] in self.DATABASES and not item["passed"]
        ]
        if corrupted:
            raise RuntimeError(
                "database corruption requires backup/restore and provider reconciliation; "
                "automatic repair refused"
            )
        repaired: list[str] = []
        for name in self.DATABASES:
            path = self.data_dir / name
            connection = sqlite3.connect(path, timeout=30)
            try:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                connection.commit()
            finally:
                connection.close()
            repaired.append(name)
        after = self.run(include_docker=False)
        return {
            "schema_version": 1,
            "completed_at": utc_now(),
            "passed": after["passed"],
            "actions": [f"checkpointed {name}" for name in repaired],
            "diagnostics": after,
        }

    def create_backup(self) -> dict[str, Any]:
        """Create a consistent local recovery archive with a hashed manifest."""

        diagnostics = self.run(include_docker=False)
        if not diagnostics["passed"]:
            raise RuntimeError("backup refused because local state diagnostics failed")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = utc_now().replace(":", "-").replace("+", "_")
        destination = self.backup_dir / f"mentat-state-{timestamp}.zip"
        sidecar_suffixes = ("-wal", "-shm", "-journal")
        database_names = set(self.DATABASES)
        non_database_sources = [
            path
            for path in sorted(self.data_dir.rglob("*"))
            if path.is_file()
            and path.name not in database_names
            and not path.name.endswith(sidecar_suffixes)
        ]
        descriptor, temp_name = tempfile.mkstemp(
            prefix=destination.name + ".",
            suffix=".tmp",
            dir=self.backup_dir,
        )
        os.close(descriptor)
        try:
            with tempfile.TemporaryDirectory(
                prefix="mentat-backup-stage-",
                dir=self.backup_dir,
            ) as staging_name:
                staging = Path(staging_name)
                for source in non_database_sources:
                    relative = source.relative_to(self.data_dir)
                    target = staging / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)

                for name in self.DATABASES:
                    source = self.data_dir / name
                    target = staging / name
                    source_connection = sqlite3.connect(
                        f"file:{source}?mode=ro",
                        uri=True,
                        timeout=30,
                    )
                    target_connection = sqlite3.connect(target, timeout=30)
                    try:
                        source_connection.backup(target_connection)
                        target_connection.commit()
                        result = target_connection.execute("PRAGMA integrity_check").fetchone()
                        if not result or result[0] != "ok":
                            raise RuntimeError(
                                f"backup snapshot integrity failed for {name}: {result}"
                            )
                    finally:
                        target_connection.close()
                        source_connection.close()

                files = [
                    path
                    for path in sorted(staging.rglob("*"))
                    if path.is_file() and not path.name.endswith(sidecar_suffixes)
                ]
                manifest = {
                    "schema_version": 1,
                    "created_at": utc_now(),
                    "sensitive": True,
                    "warning": (
                        "This archive contains local spend authority and must be "
                        "stored like a credential."
                    ),
                    "files": [
                        {
                            "path": path.relative_to(staging).as_posix(),
                            "size": path.stat().st_size,
                            "sha256": _sha256(path),
                        }
                        for path in files
                    ],
                }
                with zipfile.ZipFile(
                    temp_name,
                    "w",
                    compression=zipfile.ZIP_DEFLATED,
                    compresslevel=9,
                ) as archive:
                    for path in files:
                        archive.write(path, path.relative_to(staging).as_posix())
                    archive.writestr(
                        "backup-manifest.json",
                        json.dumps(manifest, indent=2) + "\n",
                    )
            os.replace(temp_name, destination)
            with suppress(OSError):
                os.chmod(destination, 0o600)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return {
            "schema_version": 1,
            "created_at": manifest["created_at"],
            "path": str(destination),
            "size": destination.stat().st_size,
            "sha256": _sha256(destination),
            "sensitive": True,
            "file_count": len(files),
        }
