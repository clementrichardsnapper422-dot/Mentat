from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from .models import Decision, ModelSpec, Offer, RouteRequirements, TaskClass
from .registry import ModelRegistry
from .store import BrokerStore

CODE_TERMS = {
    "code",
    "repo",
    "repository",
    "typescript",
    "javascript",
    "python",
    "powershell",
    "bug",
    "debug",
    "function",
    "class",
    "api",
    "database",
    "sql",
    "refactor",
    "tests",
    "build",
    "deploy",
    "github",
    "pull request",
    "cursor",
}
LARGE_CODE_TERMS = {
    "entire repo",
    "whole repo",
    "large refactor",
    "architecture",
    "migration",
    "multi-file",
    "production-ready",
    "end-to-end",
    "rewrite",
    "upgrade framework",
}
HIGH_RISK_TERMS = {
    "credential",
    "secret",
    "api key",
    "production database",
    "delete data",
    "payment",
    "financial",
    "security",
    "authentication",
    "authorization",
    "deploy to production",
    "merge and deploy",
    "legal",
    "medical",
}
VISION_TERMS = {"image", "photo", "picture", "screenshot", "diagram", "video"}
SIMPLE_TERMS = {
    "rename",
    "format",
    "summarize",
    "fix typo",
    "change color",
    "short answer",
    "one line",
    "translate",
}


class RoutingError(RuntimeError):
    """Raised when no model satisfies the deterministic routing policy."""


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def classify_task(
    prompt: str,
    *,
    estimated_input_tokens: int = 0,
    has_images: bool = False,
    requires_tools: bool = True,
    risk_level: str = "normal",
) -> RouteRequirements:
    normalized = re.sub(r"\s+", " ", prompt.lower()).strip()
    capabilities: set[str] = {"reasoning"}
    if requires_tools:
        capabilities.add("tools")

    explicit_high_risk = risk_level.lower() in {"high", "critical"}
    if explicit_high_risk or _contains_any(normalized, HIGH_RISK_TERMS):
        task_class: TaskClass = "high_risk"
        minimum_quality_tier = 5
        estimated_minutes = 45
    elif has_images or _contains_any(normalized, VISION_TERMS):
        task_class = "vision"
        minimum_quality_tier = 5
        capabilities.add("vision")
        estimated_minutes = 20
    elif estimated_input_tokens >= 50_000 or _contains_any(normalized, LARGE_CODE_TERMS):
        task_class = "large_code"
        minimum_quality_tier = 5
        capabilities.update({"coding", "long_context"})
        estimated_minutes = 60
    elif len(normalized) < 500 and _contains_any(normalized, SIMPLE_TERMS):
        task_class = "simple"
        minimum_quality_tier = 2
        if _contains_any(normalized, CODE_TERMS):
            capabilities.add("coding")
        estimated_minutes = 8
    elif _contains_any(normalized, CODE_TERMS):
        task_class = "code"
        minimum_quality_tier = 4
        capabilities.add("coding")
        estimated_minutes = 25
    else:
        task_class = "general"
        minimum_quality_tier = 3
        estimated_minutes = 15

    if estimated_input_tokens >= 100_000:
        capabilities.add("long_context")
    return RouteRequirements(
        task_class=task_class,
        capabilities=capabilities,
        minimum_quality_tier=minimum_quality_tier,
        estimated_input_tokens=max(0, estimated_input_tokens),
        risk_level=risk_level,
        estimated_minutes=estimated_minutes,
    )


def _quality_for(model: ModelSpec, task_class: str, store: BrokerStore) -> tuple[float, str, int]:
    summary = store.benchmark_summary(model.id, task_class)
    samples = int(summary["samples"])
    measured = summary.get("quality_score")
    if samples >= model.minimum_benchmark_samples and measured is not None:
        return float(measured), "measured", samples
    bootstrap = model.bootstrap_quality.get(task_class)
    if bootstrap is None:
        bootstrap = model.bootstrap_quality.get("general", model.quality_tier / 5)
    return float(bootstrap), "bootstrap", samples


def _candidate_models(registry: ModelRegistry, requirements: RouteRequirements) -> list[ModelSpec]:
    candidates = []
    for model in registry.enabled():
        if model.quality_tier < requirements.minimum_quality_tier:
            continue
        if requirements.task_class not in model.task_classes:
            continue
        if not requirements.capabilities.issubset(model.capabilities):
            continue
        if (
            requirements.estimated_input_tokens
            and model.context_tokens < requirements.estimated_input_tokens
        ):
            continue
        candidates.append(model)
    return candidates


def build_decision(
    *,
    prompt: str,
    registry: ModelRegistry,
    store: BrokerStore,
    offers_by_model: dict[str, list[Offer]],
    estimated_input_tokens: int = 0,
    has_images: bool = False,
    requires_tools: bool = True,
    risk_level: str = "normal",
    max_hourly_usd: float | None = None,
    max_total_usd: float | None = None,
) -> Decision:
    requirements = classify_task(
        prompt,
        estimated_input_tokens=estimated_input_tokens,
        has_images=has_images,
        requires_tools=requires_tools,
        risk_level=risk_level,
    )
    candidates = _candidate_models(registry, requirements)
    if not candidates:
        raise RoutingError(
            f"no enabled model satisfies task={requirements.task_class}, "
            f"quality_tier>={requirements.minimum_quality_tier}, "
            f"capabilities={sorted(requirements.capabilities)}"
        )

    hourly_cap = min(
        max_hourly_usd if max_hourly_usd is not None else registry.policy.max_hourly_usd,
        registry.policy.max_hourly_usd,
    )
    total_cap = min(
        max_total_usd if max_total_usd is not None else registry.policy.max_total_usd,
        registry.policy.max_total_usd,
    )

    ranked: list[tuple[ModelSpec, float, str, int, Offer | None, str, int, float]] = []
    for model in candidates:
        quality, source, samples = _quality_for(model, requirements.task_class, store)
        offers = [
            offer
            for offer in offers_by_model.get(model.id, [])
            if offer.hourly_usd <= min(hourly_cap, model.max_hourly_usd)
        ]
        offer = min(offers, key=lambda item: (item.hourly_usd, -item.reliability), default=None)
        offer_source = "live-vast" if offer else "registry-estimate"
        estimated_minutes = model.default_minutes.get(
            requirements.task_class, requirements.estimated_minutes
        )
        if offer:
            estimated_cost = offer.hourly_usd * estimated_minutes / 60
        elif model.provider == "external":
            estimated_cost = 0.0
        else:
            # The registry cap is deliberately used as the conservative estimate.
            estimated_cost = min(model.max_hourly_usd, hourly_cap) * estimated_minutes / 60
        if estimated_cost > total_cap:
            continue
        ranked.append(
            (
                model,
                quality,
                source,
                samples,
                offer,
                offer_source,
                estimated_minutes,
                estimated_cost,
            )
        )

    if not ranked:
        raise RoutingError("all compatible models exceed the current cost policy")

    best_quality = max(item[1] for item in ranked)
    allowed_gap = {
        "high_risk": 0.0,
        "vision": 0.0,
        "large_code": 0.03,
        "code": 0.08,
        "general": 0.12,
        "simple": 0.20,
    }[requirements.task_class]
    value_pool = [item for item in ranked if item[1] >= best_quality - allowed_gap]

    def rank_key(
        item: tuple[ModelSpec, float, str, int, Offer | None, str, int, float],
    ) -> tuple[float, float, float, str]:
        model, quality, _source, _samples, offer, _offer_source, _minutes, cost = item
        reliability = offer.reliability if offer else 0
        return (round(cost, 6), -quality, -reliability, model.id)

    selected = min(value_pool, key=rank_key)
    model, quality, quality_source, samples, offer, offer_source, minutes, estimated_cost = selected

    reasons = [
        f"Task classified deterministically as {requirements.task_class}.",
        f"Required capabilities: {', '.join(sorted(requirements.capabilities))}.",
        f"Required quality tier: {requirements.minimum_quality_tier}/5.",
        (
            f"Selected the lowest estimated-cost model within {allowed_gap:.0%} "
            "of the best eligible quality score."
        ),
    ]
    if quality_source == "measured":
        reasons.append(f"Quality score {quality:.3f} is based on {samples} local benchmark runs.")
    else:
        reasons.append(
            f"Quality score {quality:.3f} is provisional until {model.minimum_benchmark_samples} "
            "local benchmark runs exist."
        )
    if offer:
        reasons.append(
            f"Cheapest live compatible Vast offer is {offer.num_gpus}× {offer.gpu_name} "
            f"at ${offer.hourly_usd:.2f}/hour with reliability {offer.reliability:.3f}."
        )
    elif model.provider == "vast":
        reasons.append(
            "No live offer was available; the registry hourly cap is used conservatively."
        )
    else:
        reasons.append("Selected external fallback does not trigger a Vast GPU launch.")

    preview = re.sub(r"\s+", " ", prompt).strip()[:240]
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return Decision(
        id=str(uuid.uuid4()),
        created_at=datetime.now(UTC).isoformat(),
        prompt_preview=preview,
        prompt_digest=digest,
        task_class=requirements.task_class,
        selected_model=model.id,
        selected_model_id=model.model_id,
        fallback_chain=list(model.fallback_chain),
        reasons=reasons,
        quality_score=quality,
        quality_source=quality_source,
        benchmark_samples=samples,
        offer=offer,
        offer_source=offer_source,
        estimated_minutes=minutes,
        estimated_cost_usd=round(estimated_cost, 2),
        max_hourly_usd=round(hourly_cap, 2),
        max_total_usd=round(total_cap, 2),
        status="pending" if registry.policy.require_manual_approval else "approved",
        metadata={"requirements": requirements.as_dict()},
    )
