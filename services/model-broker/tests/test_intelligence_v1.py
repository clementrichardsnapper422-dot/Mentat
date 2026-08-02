from datetime import UTC, datetime, timedelta

import pytest

from mentat_broker.contracts import (
    BackendKind,
    EvidenceTier,
    HardwareProfile,
    ModelProfile,
    ProviderMarketSnapshot,
    RoutingMode,
)
from mentat_broker.intelligence import (
    EvidenceSummary,
    RouteEngine,
    RoutingIntelligenceError,
    TaskAnalyzer,
)


def profile(model="kimi", quality=0.95, success=0.98):
    return ModelProfile(
        profile_id=model + "-v1",
        model_id=model,
        model_version="1",
        provider="vast",
        backend=BackendKind.VAST_SERVERLESS,
        runtime_revision="r1",
        capabilities=frozenset({"text", "code", "tools"}),
        task_classes=frozenset(
            {"simple", "general", "code", "large_code", "high_risk"}
        ),
        context_tokens=256_000,
        quality_prior=quality,
        success_prior=success,
        production_eligible=True,
        maximum_hourly_usd=10,
        minimum_reliability=0.98,
    )


def market(identifier="1", price=2):
    return ProviderMarketSnapshot(
        snapshot_id="s" + identifier,
        observed_at=datetime.now(UTC).isoformat(),
        backend=BackendKind.VAST_SERVERLESS,
        offer_id=identifier,
        hourly_usd=price,
        hardware=HardwareProfile("H100", 1, 80000, True, 0.999),
        source="fake",
        expires_at=(datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        raw_digest="abc",
    )


def evidence(samples=30, quality=0.95, successes=30, cost=0.20):
    return EvidenceSummary(
        samples=samples,
        successes=successes,
        quality_mean=quality,
        quality_variance=0.0004,
        latency_mean_ms=5000,
        latency_variance=10000,
        total_cost_mean_usd=cost,
        total_cost_variance=0.0004,
        observed_at=datetime.now(UTC).isoformat(),
        tier=EvidenceTier.PRODUCTION,
        model_version="1",
        runtime_revision="r1",
    )


def test_high_risk_analysis_and_hard_eligibility():
    requirements = TaskAnalyzer().analyze(
        "Deploy this repository security migration",
        input_tokens=10000,
        tool_names=["git"],
        routing_mode=RoutingMode.BEST,
    )
    assert requirements.task_class == "high_risk"
    candidate = RouteEngine().candidate(
        requirements,
        profile(),
        market(),
        evidence(samples=500, successes=500),
    )
    assert candidate.eligible


def test_uncertain_candidate_is_rejected_before_economic_scoring():
    requirements = TaskAnalyzer().analyze(
        "Deploy payment migration",
        tool_names=["git"],
    )
    weak = EvidenceSummary(
        samples=1,
        successes=1,
        quality_mean=0.7,
        quality_variance=0.2,
    )
    candidate = RouteEngine().candidate(
        requirements,
        profile(quality=0.7, success=0.7),
        market(),
        weak,
    )
    assert not candidate.eligible
    assert any(
        "quality" in reason or "success" in reason
        for reason in candidate.hard_rejections
    )


def test_economy_mode_prefers_lower_cost_only_after_hard_requirements():
    requirements = TaskAnalyzer().analyze(
        "Fix this code bug",
        tool_names=["git"],
        routing_mode=RoutingMode.ECONOMY,
    )
    engine = RouteEngine()
    expensive = engine.candidate(
        requirements,
        profile("kimi"),
        market("1", 8),
        evidence(cost=0.80),
    )
    cheap = engine.candidate(
        requirements,
        profile("qwen", 0.93, 0.97),
        market("2", 1),
        evidence(samples=100, quality=0.93, successes=99, cost=0.05),
    )
    winner, explanation = engine.choose(requirements, [expensive, cheap])
    assert winner.profile.model_id == "qwen"
    assert explanation["rejected"] == []


def test_fallback_must_independently_satisfy_original_task():
    requirements = TaskAnalyzer().analyze(
        "Deploy security fix",
        tool_names=["git"],
    )
    bad_profile = ModelProfile(
        **{
            **profile("small").__dict__,
            "capabilities": frozenset({"text"}),
        }
    )
    fallback = RouteEngine().candidate(
        requirements,
        bad_profile,
        market(),
        evidence(),
    )
    with pytest.raises(RoutingIntelligenceError):
        RouteEngine.validate_fallback(
            requirements,
            fallback,
            remaining_budget_usd=10,
        )
