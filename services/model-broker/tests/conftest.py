from __future__ import annotations

from collections.abc import Callable

import pytest

from mentat_broker import server as broker_server
from mentat_broker.production_app import ProductionBrokerApplication
from mentat_broker.production_sessions import ProductionSessionManager
from mentat_broker.production_store import ProductionBrokerStore


@pytest.fixture
def production_application_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., ProductionBrokerApplication]:
    """Build the same production store/session composition used by broker.py.

    The hook installer mutates the server module at process startup. Tests apply
    those two dependency bindings with monkeypatch so each test remains isolated.
    """

    monkeypatch.setattr(broker_server, "BrokerStore", ProductionBrokerStore)
    monkeypatch.setattr(broker_server, "EndpointSessionManager", ProductionSessionManager)
    return ProductionBrokerApplication
