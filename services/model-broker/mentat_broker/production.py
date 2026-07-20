from __future__ import annotations

from . import server as broker_server
from .production_app import ProductionBrokerApplication
from .production_http import (
    LoopbackThreadingHTTPServer,
    production_handler_factory,
    production_read_json,
    set_max_body_bytes,
)
from .production_sessions import ProductionSessionManager
from .production_store import ProductionBrokerStore


def install_production_hooks() -> None:
    """Install the final production gates after safety and runtime hooks."""

    base_make_handler = broker_server.make_handler
    base_ui = broker_server._decision_ui

    def make_handler(application: ProductionBrokerApplication):
        set_max_body_bytes(application.registry.policy.max_request_body_bytes)
        return production_handler_factory(base_make_handler, base_ui, application)

    broker_server.BrokerStore = ProductionBrokerStore
    broker_server.EndpointSessionManager = ProductionSessionManager
    broker_server.BrokerApplication = ProductionBrokerApplication
    broker_server.ThreadingHTTPServer = LoopbackThreadingHTTPServer
    broker_server._read_json = production_read_json
    broker_server.make_handler = make_handler
