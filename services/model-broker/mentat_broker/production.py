from __future__ import annotations

from pathlib import Path

from . import server as broker_server
from .endpoint_overrides import install_endpoint_override_hooks
from .production_app import ProductionBrokerApplication
from .production_http import (
    LoopbackThreadingHTTPServer,
    production_read_json,
    set_max_body_bytes,
)
from .production_sessions import ProductionSessionManager
from .production_store import ProductionBrokerStore
from .runtime import MentatV1Runtime
from .spend import BudgetPolicy
from .v1_http import v1_handler_factory


class MentatV1ProductionApplication(ProductionBrokerApplication):
    """Existing production broker plus the durable Mentat 1.0 control plane."""

    def __init__(self, root: Path, registry_path: Path, data_dir: Path):
        super().__init__(root, registry_path, data_dir)
        policy = self.registry.policy
        try:
            self.v1 = MentatV1Runtime(
                data_dir / "mentat-v1",
                budget_policy=BudgetPolicy(
                    maximum_hourly_usd=policy.max_hourly_usd,
                    maximum_session_usd=policy.max_total_usd,
                    maximum_daily_usd=max(
                        policy.max_total_usd, policy.max_total_usd * 2
                    ),
                    maximum_monthly_usd=max(
                        policy.max_total_usd, policy.max_total_usd * 20
                    ),
                    maximum_retry_usd=max(0.01, policy.max_total_usd * 0.15),
                    maximum_fallback_usd=max(0.01, policy.max_total_usd * 0.30),
                    maximum_exploration_usd=max(0.01, policy.max_total_usd * 0.05),
                    one_paid_session=True,
                ),
            )
        except Exception:
            super().close()
            raise

    def close(self) -> None:
        try:
            super().close()
        finally:
            self.v1.close()


def install_production_hooks() -> None:
    """Install the final production gates after safety and runtime hooks."""

    install_endpoint_override_hooks()
    base_make_handler = broker_server.make_handler
    base_ui = broker_server._decision_ui

    def make_handler(application: MentatV1ProductionApplication):
        set_max_body_bytes(application.registry.policy.max_request_body_bytes)
        return v1_handler_factory(base_make_handler, base_ui, application)

    broker_server.BrokerStore = ProductionBrokerStore
    broker_server.EndpointSessionManager = ProductionSessionManager
    broker_server.BrokerApplication = MentatV1ProductionApplication
    broker_server.ThreadingHTTPServer = LoopbackThreadingHTTPServer
    broker_server._read_json = production_read_json
    broker_server.make_handler = make_handler
