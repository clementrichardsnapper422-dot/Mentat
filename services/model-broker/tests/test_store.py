from __future__ import annotations

from pathlib import Path

from mentat_broker.models import BenchmarkRecord
from mentat_broker.store import BrokerStore


def test_benchmark_summary_and_session_persistence(tmp_path: Path) -> None:
    store = BrokerStore(tmp_path / "broker.db")
    for score in (0.8, 0.9, 1.0):
        store.add_benchmark(
            BenchmarkRecord(
                model_id="qwen3-coder-30b",
                task_class="code",
                success=True,
                latency_ms=1000,
                tokens_per_second=25,
                hourly_usd=2,
                total_cost_usd=0.5,
                quality_score=score,
            )
        )
    summary = store.benchmark_summary("qwen3-coder-30b", "code")
    assert summary["samples"] == 3
    assert round(summary["quality_score"], 2) == 0.9
    assert all(record["success"] is True for record in store.list_benchmarks())

    store.upsert_session(
        "qwen3-coder-30b",
        status="ready",
        endpoint_url="http://127.0.0.1:8000/v1",
        approved_until="2099-01-01T00:00:00+00:00",
    )
    session = store.get_session("qwen3-coder-30b")
    assert session is not None
    assert session["status"] == "ready"
