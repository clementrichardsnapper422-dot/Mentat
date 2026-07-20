from __future__ import annotations

import json
from pathlib import Path

from mentat_broker.models import Decision, Offer
from mentat_broker.registry import ModelRegistry
from mentat_broker.sessions import ApprovalCoordinator, EndpointSessionManager
from mentat_broker.store import BrokerStore


def test_approved_offer_pins_worker_price_cap(tmp_path: Path) -> None:
    root = Path(__file__).parents[3]
    registry = ModelRegistry.load(root / "config" / "model-registry.json")
    store = BrokerStore(tmp_path / "broker.db")
    manager = EndpointSessionManager(
        root=root,
        state_dir=tmp_path / "state",
        registry=registry,
        store=store,
        coordinator=ApprovalCoordinator(),
    )
    model = registry.get("qwen3-coder-30b")
    decision = Decision(
        id="decision-1",
        created_at="2026-01-01T00:00:00+00:00",
        prompt_preview="Fix the API",
        prompt_digest="digest",
        task_class="code",
        selected_model=model.id,
        selected_model_id=model.model_id,
        fallback_chain=model.fallback_chain,
        reasons=[],
        quality_score=0.9,
        quality_source="bootstrap",
        benchmark_samples=0,
        offer=Offer(1, "H100 SXM", 1, 81500, 2.375, 0.995, True),
        offer_source="live-vast",
        estimated_minutes=20,
        estimated_cost_usd=0.79,
        max_hourly_usd=8,
        max_total_usd=64,
    )

    approved = manager._approved_config(model, decision)
    config = json.loads(approved.read_text(encoding="utf-8"))
    assert "dph_total<=2.3750" in config["workergroup"]["search_params"]
    assert config["policy"]["max_hourly_usd"] == 2.375
