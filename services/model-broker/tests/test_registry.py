from __future__ import annotations

from pathlib import Path

from mentat_broker.registry import ModelRegistry


def test_committed_registry_is_valid() -> None:
    root = Path(__file__).parents[3]
    registry = ModelRegistry.load(root / "config" / "model-registry.json")
    assert registry.policy.require_manual_approval is True
    assert registry.get("kimi-k2.7-code").quality_tier == 5
    assert registry.get("qwen3-coder-30b").max_hourly_usd == 8
    assert registry.get("deepseek-coder-v2-lite").max_hourly_usd == 3
