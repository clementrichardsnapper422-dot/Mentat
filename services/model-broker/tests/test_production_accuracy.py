from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mentat_broker.models import Decision, Offer
from mentat_broker.production_accuracy import (
    FinalProductionBrokerApplication,
    UpstreamRequestError,
)
from mentat_broker.production_app import ProductionBrokerApplication
from mentat_broker.sessions import SessionError

ROOT = Path(__file__).parents[3]
REGISTRY = ROOT / "config" / "model-registry.json"


def live_offer() -> Offer:
    return Offer(
        id=7,
        gpu_name="H200",
        num_gpus=8,
        gpu_ram_mb=140000,
        hourly_usd=24,
        reliability=0.995,
        verified=True,
        bw_nvlink=900,
        disk_space_gb=1000,
    )


def test_reusable_session_does_not_claim_endpoint_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MENTAT_BROKER_CLIENT_TOKEN", "client")
    monkeypatch.setenv("MENTAT_BROKER_ADMIN_TOKEN", "admin")
    monkeypatch.setenv("VAST_API_KEY", "test")
    monkeypatch.setenv("MENTAT_ENDPOINT_KIMI_K2_7_CODE", "http://127.0.0.1:1/v1")
    application = FinalProductionBrokerApplication(ROOT, REGISTRY, tmp_path / "data")
    model = application.registry.get("kimi-k2.7-code")
    now = datetime.now(UTC)
    application.store.upsert_session(
        model.id,
        status="ready",
        endpoint_url="http://127.0.0.1:1/v1",
        hourly_usd=24,
        offer=live_offer(),
        started_at=now.isoformat(),
        last_used_at=now.isoformat(),
        approved_until=(now + timedelta(minutes=30)).isoformat(),
    )
    decision = application.plan(
        {"prompt": "Review the architecture", "requires_tools": False}
    )
    assert decision.status == "approved"
    assert decision.metadata["requires_endpoint_creation"] is False
    assert not any(reason.startswith("No saved endpoint") for reason in decision.reasons)
    application.close()


def test_upstream_rejection_is_not_reported_as_approval_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MENTAT_BROKER_CLIENT_TOKEN", "client")
    monkeypatch.setenv("MENTAT_BROKER_ADMIN_TOKEN", "admin")
    monkeypatch.setenv("VAST_API_KEY", "test")
    application = FinalProductionBrokerApplication(ROOT, REGISTRY, tmp_path / "data")
    model = application.registry.get("kimi-k2.7-code")
    decision = Decision(
        id="upstream-error",
        created_at=datetime.now(UTC).isoformat(),
        prompt_preview="test",
        prompt_digest="digest",
        task_class="general",
        selected_model=model.id,
        selected_model_id=model.model_id,
        fallback_chain=[],
        reasons=[],
        quality_score=0.9,
        quality_source="bootstrap",
        benchmark_samples=0,
        offer=live_offer(),
        offer_source="live-vast",
        estimated_minutes=1,
        estimated_cost_usd=0.4,
        max_hourly_usd=32,
        max_total_usd=64,
        status="approved",
    )

    def reject(*_args, **_kwargs):
        raise SessionError('upstream rejected the request with HTTP 400: {"error":"bad"}')

    monkeypatch.setattr(ProductionBrokerApplication, "_proxy_to_model", reject)
    with pytest.raises(UpstreamRequestError, match="HTTP 400"):
        application._proxy_to_model(
            object(),
            {},
            model,
            "https://example.invalid/v1",
            decision,
            0,
        )
    application.close()
