from __future__ import annotations

from pathlib import Path

import pytest

from mentat_broker import server as broker_server
from mentat_broker.production_sessions import ProductionSessionManager
from mentat_broker.production_store import ProductionBrokerStore


@pytest.fixture(autouse=True)
def compose_production_broker_for_production_tests(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror broker.py's dependency composition in production-focused tests.

    The real entry point installs these bindings before constructing the
    application. Keep base-unit tests untouched while ensuring every
    `test_production*.py` module exercises the production store and session
    manager rather than the unhooked development defaults.
    """

    filename = Path(str(request.node.path)).name
    if not filename.startswith("test_production"):
        return
    monkeypatch.setattr(broker_server, "BrokerStore", ProductionBrokerStore)
    monkeypatch.setattr(broker_server, "EndpointSessionManager", ProductionSessionManager)
