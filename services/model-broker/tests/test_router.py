from __future__ import annotations

import json
from pathlib import Path

from mentat_broker.models import Offer
from mentat_broker.registry import ModelRegistry
from mentat_broker.router import build_decision, classify_task
from mentat_broker.store import BrokerStore


def registry(tmp_path: Path) -> ModelRegistry:
    source = Path(__file__).parents[3] / "config" / "model-registry.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    target = tmp_path / "registry.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    return ModelRegistry.load(target)


def test_large_repository_refactor_routes_to_kimi(tmp_path: Path) -> None:
    store = BrokerStore(tmp_path / "broker.db")
    decision = build_decision(
        prompt="Refactor the entire repo and deploy the production authentication migration",
        registry=registry(tmp_path),
        store=store,
        offers_by_model={},
        estimated_input_tokens=120_000,
        requires_tools=True,
    )
    assert decision.selected_model == "kimi-k2.7-code"
    assert decision.task_class == "high_risk"


def test_normal_code_task_prefers_qwen_value(tmp_path: Path) -> None:
    store = BrokerStore(tmp_path / "broker.db")
    offers = {
        "kimi-k2.7-code": [Offer(1, "H200", 8, 141000, 26.0, 0.995, True)],
        "qwen3-coder-30b": [Offer(2, "H100 SXM", 1, 81500, 2.5, 0.995, True)],
    }
    decision = build_decision(
        prompt="Fix this TypeScript API bug and add tests",
        registry=registry(tmp_path),
        store=store,
        offers_by_model=offers,
        requires_tools=True,
    )
    assert decision.selected_model == "qwen3-coder-30b"
    assert decision.offer is not None
    assert decision.offer.hourly_usd == 2.5


def test_simple_no_tool_task_can_use_deepseek(tmp_path: Path) -> None:
    store = BrokerStore(tmp_path / "broker.db")
    offers = {
        "kimi-k2.7-code": [Offer(1, "H200", 8, 141000, 26.0, 0.995, True)],
        "qwen3-coder-30b": [Offer(2, "H100 SXM", 1, 81500, 2.5, 0.995, True)],
        "deepseek-coder-v2-lite": [Offer(3, "L40S", 1, 48000, 0.8, 0.995, True)],
    }
    decision = build_decision(
        prompt="Rename this function",
        registry=registry(tmp_path),
        store=store,
        offers_by_model=offers,
        requires_tools=False,
    )
    assert decision.selected_model == "deepseek-coder-v2-lite"


def test_classifier_marks_images() -> None:
    requirements = classify_task("Review the attached screenshot", has_images=True)
    assert requirements.task_class == "vision"
    assert "vision" in requirements.capabilities
