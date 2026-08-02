import pytest

from mentat_broker.model_controls import ModelDisabledError, SettingsAwareRegistry
from mentat_broker.models import ModelConfig, Policy, Registry
from mentat_broker.settings import DesktopSettingsStore


def model(identifier: str) -> ModelConfig:
    return ModelConfig(
        id=identifier,
        display_name=identifier.title(),
        provider="fake",
        model=identifier,
        endpoint_env=f"MENTAT_ENDPOINT_{identifier.upper()}",
        endpoint_config=None,
        endpoint_api_base_path="/v1",
        capabilities=("text",),
        max_context_tokens=8192,
        min_gpus=1,
        min_gpu_ram_mb=1,
        min_reliability=0.9,
        max_hourly_usd=1,
        preferred_gpus=(),
        allows_unverified=False,
    )


def registry(tmp_path) -> Registry:
    return Registry(
        path=tmp_path / "registry.json",
        schema_version=1,
        policy=Policy(
            max_hourly_usd=10,
            max_total_usd=20,
            default_warm_minutes=10,
            max_request_body_bytes=1024,
            max_concurrent_requests=1,
        ),
        models=(model("alpha"), model("beta")),
    )


def test_disabled_model_is_removed_from_new_selection_but_remains_inspectable(tmp_path):
    settings = DesktopSettingsStore(tmp_path / "settings.json")
    settings.update({"disabled_model_ids": ["beta"]})
    controlled = SettingsAwareRegistry(registry(tmp_path), settings)

    assert [item.id for item in controlled.models] == ["alpha"]
    assert controlled.enabled_ids() == frozenset({"alpha"})
    assert [item.id for item in controlled.all_models()] == ["alpha", "beta"]
    assert controlled.get("alpha").id == "alpha"
    with pytest.raises(ModelDisabledError, match="disabled"):
        controlled.get("beta")
