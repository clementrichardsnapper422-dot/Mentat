from __future__ import annotations

from pathlib import Path

from mentat_broker.models import BenchmarkRecord
from mentat_broker.runtime_policy import (
    ContextAwareBrokerApplication,
    QualityAwareBrokerStore,
)


def test_unrated_runs_do_not_count_as_quality_samples(tmp_path: Path) -> None:
    store = QualityAwareBrokerStore(tmp_path / "quality.db")
    for _ in range(3):
        store.add_benchmark(
            BenchmarkRecord(
                model_id="qwen3-coder-30b",
                task_class="code",
                success=True,
                latency_ms=1000,
                tokens_per_second=20,
                hourly_usd=2,
                total_cost_usd=0.1,
                quality_score=None,
            )
        )
    store.add_benchmark(
        BenchmarkRecord(
            model_id="qwen3-coder-30b",
            task_class="code",
            success=True,
            latency_ms=900,
            tokens_per_second=22,
            hourly_usd=2,
            total_cost_usd=0.1,
            quality_score=0.9,
        )
    )
    summary = store.benchmark_summary("qwen3-coder-30b", "code")
    assert summary["runtime_samples"] == 4
    assert summary["samples"] == 1
    assert summary["quality_score"] == 0.9


def test_latest_user_intent_is_separate_from_full_context_size() -> None:
    application = object.__new__(ContextAwareBrokerApplication)
    messages = [
        {"role": "system", "content": "security repository tools " + "x" * 200_000},
        {"role": "user", "content": "Summarize this"},
    ]
    prompt, _ = application.routing_prompt_from_messages(messages)
    full_context, _ = application._prompt_from_messages(messages)
    assert prompt == "Summarize this"
    assert len(full_context) > 200_000
