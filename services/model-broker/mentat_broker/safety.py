from __future__ import annotations

import json
import os
import re
import secrets
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler
from typing import Any

from . import server as broker_server
from .models import Decision
from .sessions import EndpointSessionManager, SessionError
from .store import utc_now

_ORIGINAL_APPLICATION = broker_server.BrokerApplication
_ORIGINAL_DECISION_UI = broker_server._decision_ui
_ORIGINAL_READ_JSON = broker_server._read_json
_CURRENT_APPROVAL_TOKEN = ""


class SafeEndpointSessionManager(EndpointSessionManager):
    """Add cumulative budget, concurrency, authenticated health, and expiry controls."""

    def _session_not_expired(self, session: dict[str, object], now: datetime | None = None) -> bool:
        approved_until = session.get("approved_until")
        if not approved_until:
            return False
        try:
            expires = datetime.fromisoformat(str(approved_until))
        except ValueError:
            return False
        return expires > (now or datetime.now(UTC))

    def approve(self, decision: Decision, *, accept_benchmark_cost: bool) -> Decision:
        model = self.registry.get(decision.selected_model)
        maximum_active = max(1, int(os.getenv("MENTAT_MAX_ACTIVE_PAID_SESSIONS", "1")))
        now = datetime.now(UTC)
        active_paid = [
            session
            for session in self.store.list_sessions()
            if session["model_id"] != model.id
            and session["status"] in {"approved", "warming", "ready"}
            and self._session_not_expired(session, now)
            and self.registry.get(str(session["model_id"])).provider == "vast"
        ]
        if model.provider == "vast" and len(active_paid) >= maximum_active:
            names = ", ".join(str(session["model_id"]) for session in active_paid)
            raise SessionError(
                "The paid-session limit is already in use by "
                f"{names}. Cool or end that session before approving another model."
            )

        result = super().approve(
            decision,
            accept_benchmark_cost=accept_benchmark_cost,
        )
        if model.provider != "vast":
            return result

        hourly_usd = (
            decision.offer.hourly_usd
            if decision.offer
            else min(model.max_hourly_usd, decision.max_hourly_usd)
        )
        budget_hours = (
            decision.max_total_usd / hourly_usd
            if hourly_usd > 0
            else self.registry.policy.max_session_hours
        )
        approved_hours = min(self.registry.policy.max_session_hours, budget_hours)
        approved_until = now + timedelta(hours=approved_hours)
        session = self.store.get_session(model.id) or {}
        self.store.upsert_session(
            model.id,
            status=str(session.get("status") or "approved"),
            endpoint_url=(str(session["endpoint_url"]) if session.get("endpoint_url") else None),
            hourly_usd=hourly_usd,
            decision_id=decision.id,
            started_at=(str(session["started_at"]) if session.get("started_at") else utc_now()),
            last_used_at=(
                str(session["last_used_at"]) if session.get("last_used_at") else utc_now()
            ),
            approved_until=approved_until.isoformat(),
        )
        return result

    def is_approved(self, model_id: str) -> bool:
        session = self.store.get_session(model_id)
        if not session or session["status"] not in {"approved", "warming", "ready"}:
            return False
        return self._session_not_expired(session)

    def _probe(self, base_url: str) -> bool:
        api_key = os.getenv("VAST_API_KEY") or "EMPTY"
        targets = [
            base_url.rstrip("/") + "/models",
            base_url.rstrip("/").removesuffix("/v1") + "/health",
        ]
        for target in targets:
            request = urllib.request.Request(
                target,
                method="GET",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    if 200 <= response.status < 300:
                        return True
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
                continue
        return False

    def _sweep_loop(self) -> None:
        while not self._stop_event.wait(30):
            now = datetime.now(UTC)
            for session in self.store.list_sessions():
                if session["status"] not in {"approved", "ready"}:
                    continue
                last_used_raw = session.get("last_used_at")
                if not last_used_raw:
                    continue
                try:
                    last_used = datetime.fromisoformat(str(last_used_raw))
                except ValueError:
                    continue
                idle_minutes = (now - last_used).total_seconds() / 60
                expired = not self._session_not_expired(session, now)
                if not expired and idle_minutes < self.registry.policy.idle_shutdown_minutes:
                    continue
                model = self.registry.get(str(session["model_id"]))
                if model.provider != "vast":
                    continue
                try:
                    self._lifecycle(model, "cool")
                    self.store.upsert_session(model.id, status="cooled")
                except Exception as exc:
                    self.store.upsert_session(model.id, status="failed", error=str(exc))


TOOL_ACTION_TERMS = {
    "browse",
    "calendar",
    "commit",
    "create file",
    "delete",
    "deploy",
    "edit",
    "email",
    "file",
    "folder",
    "github",
    "install",
    "merge",
    "open the",
    "pull request",
    "rename",
    "repo",
    "repository",
    "run",
    "search",
    "send",
    "terminal",
    "test",
    "update",
}


class SafeBrokerApplication(_ORIGINAL_APPLICATION):
    def __init__(self, *args: Any, **kwargs: Any):
        global _CURRENT_APPROVAL_TOKEN
        self.approval_token = secrets.token_urlsafe(32)
        _CURRENT_APPROVAL_TOKEN = self.approval_token
        super().__init__(*args, **kwargs)

    @staticmethod
    def task_requires_tools(prompt: str, tools_available: bool) -> bool:
        if not tools_available:
            return False
        normalized = re.sub(r"\s+", " ", prompt.lower()).strip()
        return any(term in normalized for term in TOOL_ACTION_TERMS)

    def routing_prompt_from_messages(self, messages: list[dict[str, Any]]) -> tuple[str, bool]:
        user_messages = [
            message for message in messages if str(message.get("role") or "") == "user"
        ]
        routing_messages = user_messages[-1:] if user_messages else messages[-1:]
        return self._prompt_from_messages(routing_messages)

    def prepare_chat(self, payload: dict[str, Any]):
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise ValueError("messages must be an array")
        prompt, has_images = self.routing_prompt_from_messages(messages)
        explicit_tools = payload.get("mentat_requires_tools")
        requires_tools = (
            bool(explicit_tools)
            if explicit_tools is not None
            else self.task_requires_tools(prompt, bool(payload.get("tools")))
        )
        estimated_tokens = max(1, len(prompt) // 4)
        decision = self.plan(
            {
                "prompt": prompt,
                "has_images": has_images,
                "requires_tools": requires_tools,
                "estimated_input_tokens": estimated_tokens,
                "risk_level": payload.get("mentat_risk_level", "normal"),
                "max_hourly_usd": payload.get("mentat_max_hourly_usd"),
                "max_total_usd": payload.get("mentat_max_total_usd"),
            }
        )
        model = self.registry.get(decision.selected_model)
        if decision.status == "pending":
            resolved = self.coordinator.wait_for_terminal(
                self.store,
                decision.id,
                self.registry.policy.approval_timeout_seconds,
            )
            if not resolved or resolved.status in {"pending", "warming"}:
                self.store.update_decision_status(
                    decision.id,
                    "timed_out",
                    error="approval timed out",
                    completed_at=utc_now(),
                )
                raise SessionError(f"compute approval timed out for decision {decision.id}")
            if resolved.status == "rejected":
                raise PermissionError(f"compute decision {decision.id} was rejected")
            if resolved.status == "failed":
                raise SessionError(resolved.error or "endpoint approval failed")
            decision = resolved
        endpoint = self.sessions.wait_until_ready(model)
        return decision, model, endpoint

    def plan(self, payload: dict[str, Any]) -> Decision:
        decision = super().plan(payload)
        selected = self.registry.get(decision.selected_model)
        requires_creation = (
            selected.provider == "vast" and not self.sessions.endpoint_state_path(selected).exists()
        )
        decision.metadata["requires_endpoint_creation"] = requires_creation
        decision.metadata["approved_price_ceiling_usd"] = (
            decision.offer.hourly_usd if decision.offer else selected.max_hourly_usd
        )
        if requires_creation:
            decision.reasons.append(
                "This model has no saved Vast endpoint yet. Approval may launch the profile's "
                "initial benchmark worker before the task session starts."
            )
        self.store.save_decision(decision)
        return decision

    def approve(self, decision_id: str, payload: dict[str, Any]) -> Decision:
        supplied = str(payload.pop("_approval_token", ""))
        if not secrets.compare_digest(supplied, self.approval_token):
            raise SessionError("invalid local approval token")
        return super().approve(decision_id, payload)


def safe_read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_type = handler.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    length = int(handler.headers.get("Content-Length") or 0)
    if length and content_type != "application/json":
        raise ValueError("Content-Type must be application/json")
    return _ORIGINAL_READ_JSON(handler)


def secure_decision_ui() -> bytes:
    try:
        original = _ORIGINAL_DECISION_UI().decode("utf-8")
    except TypeError:
        # Supports development trees where the base UI already accepts a token.
        return _ORIGINAL_DECISION_UI(_CURRENT_APPROVAL_TOKEN)
    token_json = json.dumps(_CURRENT_APPROVAL_TOKEN)
    original = original.replace(
        "const list = document.getElementById('list');",
        "const list = document.getElementById('list');\nconst approvalToken = " + token_json + ";",
    )
    original = original.replace(
        "async function action(id, verb, body={}) {",
        "async function action(id, verb, body={}) {\n  body._approval_token = approvalToken;",
    )
    original = original.replace(
        "Approve this model and GPU plan? This may create or warm paid Vast compute up to the displayed policy caps.",
        "Approve this model and GPU plan? A new endpoint may run an initial benchmark worker. Paid compute remains limited by the displayed price and session caps.",
    )
    original = original.replace(
        '<div><div class="label">GPU offer</div><div class="value">${offerText}</div></div>',
        '<div><div class="label">GPU reference / price ceiling</div><div class="value">${offerText}</div></div>',
    )
    original = original.replace(
        "`${offer.num_gpus}× ${escapeHtml(offer.gpu_name)} · ${money(offer.hourly_usd)}/hr`",
        "`${offer.num_gpus}× ${escapeHtml(offer.gpu_name)} reference · maximum ${money(offer.hourly_usd)}/hr`",
    )
    return original.encode("utf-8")


def install_safety_hooks() -> None:
    """Install hard safety hooks before the broker application is constructed."""

    broker_server.EndpointSessionManager = SafeEndpointSessionManager
    broker_server.BrokerApplication = SafeBrokerApplication
    broker_server._read_json = safe_read_json
    broker_server._decision_ui = secure_decision_ui
