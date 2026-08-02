import pytest

from mentat_broker.backends import (
    BackendError,
    BackendRegistry,
    ExperimentalDirectBackend,
    FakeBackend,
)
from mentat_broker.contracts import BackendKind


def test_experimental_direct_backend_cannot_be_selected_for_production():
    registry = BackendRegistry()
    registry.register(FakeBackend())
    registry.register(ExperimentalDirectBackend())
    assert registry.get(BackendKind.FAKE).capabilities.production_eligible
    with pytest.raises(BackendError, match="production gates"):
        registry.get(BackendKind.VAST_DIRECT)
