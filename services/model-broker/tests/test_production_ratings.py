from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mentat_broker.models import BenchmarkRecord, Decision, Offer
from mentat_broker.production_store import ProductionBrokerStore


def completed_decision() -> Decision:
    return Decision(
        id="rated-decision",
        created_at=datetime.now(UTC).isoformat(),
        prompt_preview="Summarize this architecture",
        prompt_digest="digest",
        task_class="general",
        selected_model="kimi-k2.7-code",
        selected_model_id="moonshotai/Kimi-K2.7-Code",
        fallback_chain=[],
        reasons=[],
        quality_score=0.94,
        quality_source="bootstrap",
        benchmark_samples=0,
        offer=Offer(
            id=1,
            gpu_name="H200",
            num_gpus=8,
            gpu_ram_mb=140000,
            hourly_usd=24,
            reliability=0.995,
            verified=True,
            bw_nvlink=900,
            disk_space_gb=1000,
        ),
        offer_source="live-vast",
        estimated_minutes=15,
        estimated_cost_usd=6,
        max_hourly_usd=32,
        max_total_usd=64,
        status="completed",
        completed_at=datetime.now(UTC).isoformat(),
        metadata={},
    )


def test_rating_is_unique_and_does_not_change_runtime_metrics(tmp_path: Path) -> None:
    store = ProductionBrokerStore(tmp_path / "broker.sqlite3")
    decision = completed_decision()
    store.save_decision(decision)
    store.add_benchmark(
        BenchmarkRecord(
            model_id=decision.selected_model,
            task_class=decision.task_class,
            success=True,
            latency_ms=1200,
            tokens_per_second=42,
            hourly_usd=24,
            total_cost_usd=0.5,
            quality_score=None,
            notes="runtime telemetry",
        )
    )

    before = store.benchmark_summary(decision.selected_model, decision.task_class)
    assert before["runtime_samples"] == 1
    assert before["samples"] == 0
    assert before["latency_ms"] == 1200

    saved = store.rate_decision(decision.id, 0.8, "Solid answer")
    assert saved["quality_score"] == 0.8
    assert store.get_rating(decision.id)["notes"] == "Solid answer"

    after = store.benchmark_summary(decision.selected_model, decision.task_class)
    assert after["runtime_samples"] == 1
    assert after["samples"] == 1
    assert after["quality_score"] == 0.8
    assert after["latency_ms"] == 1200
    assert after["tokens_per_second"] == 42

    with pytest.raises(ValueError, match="already has"):
        store.rate_decision(decision.id, 1.0)
    store.close()


def test_pending_decision_cannot_be_rated(tmp_path: Path) -> None:
    store = ProductionBrokerStore(tmp_path / "broker.sqlite3")
    decision = completed_decision()
    decision.status = "pending"
    decision.completed_at = None
    store.save_decision(decision)
    with pytest.raises(ValueError, match="completed"):
        store.rate_decision(decision.id, 0.5)
    store.close()
