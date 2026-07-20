from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from .models import Decision, ModelSpec
from .production_app import ProductionBrokerApplication
from .sessions import SessionError
from .store import utc_now


class UpstreamRequestError(RuntimeError):
    """Raised when an approved model endpoint rejects a proxied request."""


class FinalProductionBrokerApplication(ProductionBrokerApplication):
    """Correct final user-visible state after the core production policy runs."""

    def plan(self, payload: dict) -> Decision:
        decision = super().plan(payload)
        selected = self.registry.get(decision.selected_model)
        if self.sessions.is_approved(selected.id):
            decision.metadata["requires_endpoint_creation"] = False
            decision.reasons = [
                reason
                for reason in decision.reasons
                if not reason.startswith("No saved endpoint exists for this model")
            ]
            self.store.save_decision(decision)
        return decision

    def _proxy_to_model(
        self,
        handler: BaseHTTPRequestHandler,
        payload: dict,
        model: ModelSpec,
        base_url: str,
        decision: Decision,
        started: float,
    ) -> None:
        try:
            super()._proxy_to_model(
                handler,
                payload,
                model,
                base_url,
                decision,
                started,
            )
        except SessionError as exc:
            if str(exc).startswith("upstream rejected the request with HTTP"):
                raise UpstreamRequestError(str(exc)) from exc
            raise
        self.store.upsert_session(
            model.id,
            status="ready",
            endpoint_url=base_url,
            last_used_at=utc_now(),
        )
