import json
import zipfile

import pytest
from mentat_broker.diagnostics import DiagnosticsService
from mentat_broker.runtime import MentatV1Runtime


def test_live_runtime_diagnostics_repair_and_backup(tmp_path):
    runtime = MentatV1Runtime(tmp_path / "runtime")
    try:
        diagnostics = runtime.run_diagnostics(include_docker=False)
        assert diagnostics["passed"] is True

        repair = runtime.safe_repair()
        assert repair["passed"] is True

        backup = runtime.create_backup()
        assert backup["sensitive"] is True
        assert backup["file_count"] >= 5
        with zipfile.ZipFile(backup["path"]) as archive:
            names = set(archive.namelist())
            assert "spend.sqlite3" in names
            assert "executions.sqlite3" in names
            assert "spend-authority.key" in names
            assert "desktop-settings.json" in names
            assert "backup-manifest.json" in names
            assert not any(name.endswith(("-wal", "-shm", "-journal")) for name in names)
            manifest = json.loads(archive.read("backup-manifest.json"))
            assert manifest["sensitive"] is True
            assert all(item["sha256"] for item in manifest["files"])
    finally:
        runtime.close()


def test_corrupt_database_is_reported_and_automatic_repair_refuses(tmp_path):
    data_dir = tmp_path / "runtime"
    runtime = MentatV1Runtime(data_dir)
    runtime.close()
    (data_dir / "spend.sqlite3").write_bytes(b"not a sqlite database")

    service = DiagnosticsService(data_dir)
    report = service.run(include_docker=False)
    assert report["passed"] is False
    failed = {item["name"]: item for item in report["checks"] if not item["passed"]}
    assert "spend.sqlite3" in failed
    assert failed["spend.sqlite3"]["repairable"] is True
    with pytest.raises(RuntimeError, match="automatic repair refused"):
        service.safe_repair()
    with pytest.raises(RuntimeError, match="diagnostics failed"):
        service.create_backup()
