"""Evidence-aware deterministic routing intelligence for Mentat 1.0."""

from __future__ import annotations

import hashlib
import math
import random
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from .contracts import (
    EvidenceTier,
    ExecutionCandidate,
    ModelProfile,
    ProviderMarketSnapshot,
    RangeEstimate,
    RiskLevel,
    RoutingMode,
    TaskRequirements,
)


class RoutingIntelligenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvidenceSummary:
    samples: int = 0
    successes: int = 0
    quality_mean: float | None = None
    quality_variance: float | None = None
    latency_mean_ms: float | None = None
    latency_variance: float | None = None
    total_cost_mean_usd: float | None = None
    total_cost_variance: float | None = None
    observed_at: str | None = None
    tier: EvidenceTier = EvidenceTier.PRIOR
    model_version: str | None = None
    runtime_revision: str | None = None

    @property
    def success_rate(self) -> float | None:
        return self.successes / self.samples if self.samples > 0 else None


@dataclass(frozen=True)
class FailureObservation:
    key: str
    code: str
    observed_at: str
    severity: str = "normal"


@dataclass
class CircuitState:
    failures: list[datetime] = field(default_factory=list)
    opened_until: datetime | None = None
    reason: str | None = None


class CircuitBreakerRegistry:
    def __init__(
        self,
        *,
        threshold: int = 3,
        window: timedelta = timedelta(minutes=10),
        cooldown: timedelta = timedelta(minutes=15),
    ) -> None:
        self.threshold = threshold
        self.window = window
        self.cooldown = cooldown
        self._states: dict[str, CircuitState] = {}

    def record_failure(
        self,
        observation: FailureObservation,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(UTC)
        state = self._states.setdefault(observation.key, CircuitState())
        cutoff = current - self.window
        state.failures = [value for value in state.failures if value >= cutoff]
        state.failures.append(current)
        if observation.severity == "critical" or len(state.failures) >= self.threshold:
            state.opened_until = current + self.cooldown
            state.reason = observation.code

    def record_success(self, key: str) -> None:
        state = self._states.get(key)
        if state:
            state.failures.clear()
            state.opened_until = None
            state.reason = None

    def is_open(self, key: str, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        state = self._states.get(key)
        if not state or not state.opened_until:
            return False
        if current >= state.opened_until:
            state.opened_until = None
            state.reason = None
            state.failures.clear()
            return False
        return True

    def describe(self, now: datetime | None = None) -> dict[str, Any]:
        current = now or datetime.now(UTC)
        return {
            key: {
                "open": self.is_open(key, current),
                "opened_until": (
                    state.opened_until.isoformat() if state.opened_until else None
                ),
                "reason": state.reason,
                "recent_failures": len(state.failures),
            }
            for key, state in sorted(self._states.items())
        }


class TaskAnalyzer:
    HIGH_RISK_TERMS = {
        "deploy",
        "production",
        "payment",
        "credential",
        "secret",
        "security",
        "database migration",
        "delete",
        "merge",
        "release",
        "billing",
    }
    CODE_TERMS = {
        "code",
        "repository",
        "repo",
        "bug",
        "typescript",
        "python",
        "api",
        "test",
        "refactor",
        "github",
    }

    def analyze(
        self,
        prompt: str,
        *,
        input_tokens: int = 0,
        reserved_output_tokens: int = 4096,
        tool_names: Iterable[str] = (),
        repository_files: int = 0,
        attachment_bytes: int = 0,
        has_images: bool = False,
        routing_mode: RoutingMode = RoutingMode.BALANCED,
        maximum_total_cost_usd: float = 64.0,
        maximum_latency_ms: int = 30 * 60 * 1000,
    ) -> TaskRequirements:
        normalized = " ".join(prompt.lower().split())
        capabilities = {"text"}
        tool_list = sorted(set(tool_names))
        if tool_list:
            capabilities.add("tools")
        if has_images:
            capabilities.add("vision")
        if any(term in normalized for term in self.CODE_TERMS) or repository_files:
            capabilities.add("code")
        high_risk = any(term in normalized for term in self.HIGH_RISK_TERMS)
        if has_images:
            task_class = "vision"
        elif high_risk:
            task_class = "high_risk"
        elif repository_files >= 500 or input_tokens >= 100_000:
            task_class = "large_code"
        elif "code" in capabilities:
            task_class = "code"
        elif len(normalized) < 80 and not tool_list:
            task_class = "simple"
        else:
            task_class = "general"
        if high_risk or repository_files > 5_000 or attachment_bytes > 500_000_000:
            risk = RiskLevel.HIGH
        elif tool_list:
            risk = RiskLevel.NORMAL
        else:
            risk = RiskLevel.LOW
        minimum_quality = {
            RiskLevel.LOW: 0.62,
            RiskLevel.NORMAL: 0.72,
            RiskLevel.HIGH: 0.86,
            RiskLevel.CRITICAL: 0.93,
        }[risk]
        minimum_success = {
            RiskLevel.LOW: 0.70,
            RiskLevel.NORMAL: 0.82,
            RiskLevel.HIGH: 0.94,
            RiskLevel.CRITICAL: 0.98,
        }[risk]
        return TaskRequirements(
            task_class=task_class,
            capabilities=frozenset(capabilities),
            input_tokens=max(0, int(input_tokens)),
            reserved_output_tokens=max(1, int(reserved_output_tokens)),
            minimum_quality=minimum_quality,
            minimum_success_probability=minimum_success,
            maximum_total_cost_usd=max(0, float(maximum_total_cost_usd)),
            maximum_latency_ms=max(1, int(maximum_latency_ms)),
            risk_level=risk,
            verification_strength=(
                "strong" if risk in {RiskLevel.HIGH, RiskLevel.CRITICAL} else "standard"
            ),
            reversible=not high_risk,
            blast_radius=(
                "production"
                if high_risk
                else ("repository" if repository_files else "conversation")
            ),
            repository_files=max(0, int(repository_files)),
            attachment_bytes=max(0, int(attachment_bytes)),
            routing_mode=routing_mode,
            metadata={
                "tool_names": tool_list,
                "prompt_digest": hashlib.sha256(prompt.encode()).hexdigest(),
            },
        )


class PredictionEngine:
    MAX_EVIDENCE_AGE = timedelta(days=45)

    @staticmethod
    def _age_penalty(observed_at: str | None, now: datetime) -> float:
        if not observed_at:
            return 0.12
        try:
            value = datetime.fromisoformat(observed_at)
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
        except ValueError:
            return 0.15
        age = max(timedelta(), now - value)
        return min(0.25, 0.25 * age / PredictionEngine.MAX_EVIDENCE_AGE)

    @staticmethod
    def _half_width(samples: int, variance: float | None, floor: float) -> float:
        if samples <= 0:
            return max(0.18, floor)
        standard_error = math.sqrt(max(variance or floor**2, floor**2) / samples)
        return max(floor, min(0.35, 1.96 * standard_error))

    def predict(
        self,
        profile: ModelProfile,
        market: ProviderMarketSnapshot | None,
        evidence: EvidenceSummary,
        requirements: TaskRequirements,
        *,
        now: datetime | None = None,
    ) -> tuple[RangeEstimate, RangeEstimate, RangeEstimate, RangeEstimate]:
        current = now or datetime.now(UTC)
        version_match = (
            evidence.model_version in {None, profile.model_version}
            and evidence.runtime_revision in {None, profile.runtime_revision}
        )
        samples = evidence.samples if version_match else 0
        penalty = self._age_penalty(evidence.observed_at, current)
        quality_center = (
            evidence.quality_mean
            if samples and evidence.quality_mean is not None
            else profile.quality_prior
        )
        quality_center = max(0.0, min(1.0, quality_center - penalty / 2))
        quality_half = self._half_width(samples, evidence.quality_variance, 0.04) + penalty
        quality = RangeEstimate(
            max(0.0, quality_center - quality_half),
            quality_center,
            min(1.0, quality_center + quality_half / 2),
            "probability",
        )
        success_center = (
            evidence.success_rate
            if samples and evidence.success_rate is not None
            else profile.success_prior
        )
        success_center = max(0.0, min(1.0, success_center - penalty / 2))
        if samples:
            z = 1.96
            denominator = 1 + z * z / samples
            adjusted = (success_center + z * z / (2 * samples)) / denominator
            half = z * math.sqrt(
                (success_center * (1 - success_center) + z * z / (4 * samples))
                / samples
            ) / denominator
            success_low = max(0.0, adjusted - half - penalty)
            success_high = min(1.0, adjusted + half)
        else:
            success_low = max(0.0, success_center - 0.20 - penalty)
            success_high = min(1.0, success_center + 0.10)
        success = RangeEstimate(success_low, success_center, success_high, "probability")
        latency_center = evidence.latency_mean_ms or max(
            1_000.0, requirements.required_context_tokens * 1.5
        )
        latency_half = self._half_width(
            samples,
            evidence.latency_variance,
            max(250.0, latency_center * 0.12),
        )
        latency = RangeEstimate(
            max(0.0, latency_center - latency_half),
            latency_center,
            latency_center + latency_half * 1.5,
            "milliseconds",
        )
        if evidence.total_cost_mean_usd is not None and samples:
            cost_center = max(0.0, evidence.total_cost_mean_usd)
        elif market:
            cost_center = market.hourly_usd * max(
                1 / 60, latency.expected / 3_600_000
            )
        else:
            cost_center = 0.0
        cost_half = self._half_width(
            samples,
            evidence.total_cost_variance,
            max(0.01, cost_center * 0.20),
        )
        cost = RangeEstimate(
            max(0.0, cost_center - cost_half / 2),
            cost_center,
            cost_center + cost_half * 2,
            "USD",
        )
        return quality, success, cost, latency


class RouteEngine:
    def __init__(
        self,
        *,
        circuits: CircuitBreakerRegistry | None = None,
        exploration_seed: int = 0,
    ) -> None:
        self.circuits = circuits or CircuitBreakerRegistry()
        self.predictor = PredictionEngine()
        self._random = random.Random(exploration_seed)

    def candidate(
        self,
        requirements: TaskRequirements,
        profile: ModelProfile,
        market: ProviderMarketSnapshot | None,
        evidence: EvidenceSummary,
        *,
        now: datetime | None = None,
    ) -> ExecutionCandidate:
        quality, success, cost, latency = self.predictor.predict(
            profile, market, evidence, requirements, now=now
        )
        hard: list[str] = []
        if not profile.production_eligible:
            hard.append("model profile is not production eligible")
        if requirements.task_class not in profile.task_classes:
            hard.append("task class is unsupported")
        missing = requirements.capabilities - profile.capabilities
        if missing:
            hard.append("missing capabilities: " + ", ".join(sorted(missing)))
        if requirements.required_context_tokens > profile.context_tokens:
            hard.append("declared context limit is insufficient")
        if market is None and profile.backend.value.startswith("vast"):
            hard.append("fresh provider offer is required")
        if market and market.hourly_usd > profile.maximum_hourly_usd:
            hard.append("offer exceeds model profile hourly ceiling")
        if market and market.hardware.reliability < profile.minimum_reliability:
            hard.append("host reliability is below policy")
        if quality.low < requirements.minimum_quality:
            hard.append("conservative quality lower bound is below requirement")
        if success.low < requirements.minimum_success_probability:
            hard.append("conservative success lower bound is below requirement")
        if cost.high > requirements.maximum_total_cost_usd:
            hard.append("conservative total-cost upper bound exceeds budget")
        if latency.high > requirements.maximum_latency_ms:
            hard.append("conservative latency upper bound exceeds requirement")
        for key in (profile.profile_id, profile.model_id, profile.backend.value):
            if self.circuits.is_open(key, now):
                hard.append(f"circuit breaker is open for {key}")
        raw_id = "|".join(
            [
                profile.profile_id,
                market.offer_id if market else "no-offer",
                requirements.task_class,
                requirements.routing_mode.value,
            ]
        )
        return ExecutionCandidate(
            candidate_id=hashlib.sha256(raw_id.encode()).hexdigest()[:24],
            profile=profile,
            market=market,
            quality=quality,
            success_probability=success,
            total_cost_usd=cost,
            latency_ms=latency,
            evidence_tier=evidence.tier,
            evidence_samples=evidence.samples,
            evidence_observed_at=evidence.observed_at,
            eligible=not hard,
            hard_rejections=tuple(hard),
        )

    def rank(
        self,
        requirements: TaskRequirements,
        candidates: Iterable[ExecutionCandidate],
        *,
        exploration_enabled: bool = False,
        exploration_budget_remaining_usd: float = 0.0,
    ) -> list[ExecutionCandidate]:
        weights = {
            RoutingMode.BEST: {
                "quality": 0.48,
                "success": 0.32,
                "cost": 0.06,
                "speed": 0.06,
                "evidence": 0.08,
            },
            RoutingMode.BALANCED: {
                "quality": 0.31,
                "success": 0.27,
                "cost": 0.18,
                "speed": 0.12,
                "evidence": 0.12,
            },
            RoutingMode.ECONOMY: {
                "quality": 0.20,
                "success": 0.22,
                "cost": 0.36,
                "speed": 0.10,
                "evidence": 0.12,
            },
            RoutingMode.MANUAL: {
                "quality": 0.25,
                "success": 0.25,
                "cost": 0.20,
                "speed": 0.10,
                "evidence": 0.20,
            },
        }[requirements.routing_mode]
        scored: list[ExecutionCandidate] = []
        for candidate in candidates:
            if not candidate.eligible:
                continue
            components = self._score_components(candidate)
            score = sum(components[name] * weight for name, weight in weights.items())
            exploration = (
                exploration_enabled
                and requirements.risk_level == RiskLevel.LOW
                and requirements.reversible
                and candidate.evidence_samples < 5
                and candidate.total_cost_usd.high <= exploration_budget_remaining_usd
            )
            if exploration:
                score += self._random.uniform(0.0, 0.025)
            scored.append(
                ExecutionCandidate(
                    **{
                        **candidate.__dict__,
                        "score": round(score, 8),
                        "score_components": components,
                        "exploration": exploration,
                    }
                )
            )
        return sorted(scored, key=lambda item: item.score or float("-inf"), reverse=True)

    def choose(
        self,
        requirements: TaskRequirements,
        candidates: Iterable[ExecutionCandidate],
        **rank_options: Any,
    ) -> tuple[ExecutionCandidate, dict[str, Any]]:
        all_candidates = list(candidates)
        ranked = self.rank(requirements, all_candidates, **rank_options)
        if not ranked:
            reasons = {
                item.candidate_id: list(item.hard_rejections) for item in all_candidates
            }
            raise RoutingIntelligenceError(f"no eligible execution candidate: {reasons}")
        winner = ranked[0]
        return winner, {
            "policy_version": 1,
            "routing_mode": requirements.routing_mode.value,
            "winner": winner.as_dict(),
            "alternatives": [item.as_dict() for item in ranked[1:]],
            "rejected": [item.as_dict() for item in all_candidates if not item.eligible],
            "requirements": requirements.as_dict(),
        }

    @staticmethod
    def validate_fallback(
        original: TaskRequirements,
        fallback: ExecutionCandidate,
        *,
        remaining_budget_usd: float,
    ) -> None:
        if not fallback.eligible:
            raise RoutingIntelligenceError("fallback is not independently eligible")
        if fallback.total_cost_usd.high > remaining_budget_usd:
            raise RoutingIntelligenceError("fallback exceeds remaining approved budget")
        if original.capabilities - fallback.profile.capabilities:
            raise RoutingIntelligenceError(
                "fallback does not satisfy original capabilities"
            )
        if original.task_class not in fallback.profile.task_classes:
            raise RoutingIntelligenceError("fallback does not satisfy original task class")
        if fallback.quality.low < original.minimum_quality:
            raise RoutingIntelligenceError("fallback quality lower bound is insufficient")
        if fallback.success_probability.low < original.minimum_success_probability:
            raise RoutingIntelligenceError("fallback success lower bound is insufficient")

    @staticmethod
    def routing_regret(
        selected: ExecutionCandidate,
        alternatives: Iterable[ExecutionCandidate],
        *,
        actual_quality: float,
        actual_cost_usd: float,
    ) -> dict[str, Any]:
        eligible = [item for item in alternatives if item.eligible]
        expected_best = max(
            [selected, *eligible],
            key=lambda item: (item.quality.expected, -item.total_cost_usd.expected),
        )
        return {
            "selected_candidate_id": selected.candidate_id,
            "counterfactual_candidate_id": expected_best.candidate_id,
            "quality_prediction_error": actual_quality - selected.quality.expected,
            "cost_prediction_error_usd": (
                actual_cost_usd - selected.total_cost_usd.expected
            ),
            "expected_quality_regret": max(
                0.0, expected_best.quality.expected - actual_quality
            ),
            "expected_cost_regret_usd": max(
                0.0, actual_cost_usd - expected_best.total_cost_usd.expected
            ),
        }

    @staticmethod
    def _score_components(candidate: ExecutionCandidate) -> dict[str, float]:
        cost = 1 / (1 + candidate.total_cost_usd.high)
        speed = 1 / (1 + candidate.latency_ms.high / 10_000)
        evidence = min(1.0, math.log1p(candidate.evidence_samples) / math.log(31))
        tier_bonus = {
            EvidenceTier.PRIOR: 0.0,
            EvidenceTier.BENCHMARK: 0.10,
            EvidenceTier.PRODUCTION: 0.18,
            EvidenceTier.LIVE_VALIDATED: 0.25,
        }[candidate.evidence_tier]
        return {
            "quality": candidate.quality.low,
            "success": candidate.success_probability.low,
            "cost": cost,
            "speed": speed,
            "evidence": min(1.0, evidence + tier_bonus),
        }


def classify_failure(error_code: str, message: str = "") -> dict[str, Any]:
    normalized = f"{error_code} {message}".lower()
    if any(term in normalized for term in ("timeout", "connection reset", "network")):
        category = "transport"
        action = "reconcile_before_retry"
    elif any(term in normalized for term in ("rate limit", "429")):
        category = "rate_limit"
        action = "retry_after_backoff_if_lease_valid"
    elif any(term in normalized for term in ("401", "403", "auth", "credential")):
        category = "authentication"
        action = "do_not_retry"
    elif any(term in normalized for term in ("billing", "price", "cost")):
        category = "billing"
        action = "activate_kill_switch_and_reconcile"
    elif any(term in normalized for term in ("malformed", "schema", "parse")):
        category = "protocol"
        action = "demote_profile_and_fail_closed"
    else:
        category = "unknown"
        action = "bounded_retry_only_if_no_paid_mutation"
    return {
        "category": category,
        "recommended_action": action,
        "circuit_key": (
            re.sub(r"[^a-z0-9_.-]+", "-", error_code.lower()).strip("-")
            or "unknown"
        ),
    }
