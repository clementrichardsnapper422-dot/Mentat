import json

import pytest
from mentat_broker.model_controls import ModelDisabledError, SettingsAwareRegistry
from mentat_broker.registry import ModelRegistry
from mentat_broker.settings import DesktopSettingsStore


def registry(tmp_path) -> ModelRegistry:
    endpoint = tmp_path / "endpoint.json"
    endpoint.write_text("{}\n", encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    path = config_dir / "model-registry.json"
    path.write_text(
        json.dumps(
            {
                "policy": {
                    "primary_model_id": "alpha",
                    "max_hourly_usd": 10,
                    "max_total_usd": 20,
                },
                "models": [
                    {
                        "id": identifier,
                        "display_name": identifier.title(),
                        "model_id": f"test/{identifier}",
                        "provider": "vast",
                        "enabled": True,
                        "quality_tier": 3,
                        "bootstrap_quality": {"general": 0.8},
                        "capabilities": ["reasoning"],
                        "task_classes": ["general"],
                        "context_tokens": 8192,
                        "num_gpus": 1,
                        "min_gpu_ram_mb": 1,
                        "min_disk_gb": 1,
                        "gpu_names": ["fake"],
                        "max_hourly_usd": 1,
                        "endpoint_config": "endpoint.json",
                        "state_name": f"{identifier}.json",
                        "fallback_chain": [],
                        "default_minutes": {"general": 1},
                    }
                    for identifier in ("alpha", "beta")
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return ModelRegistry.load(path)


def test_disabled_model_is_removed_from_new_selection_but_remains_inspectable(tmp_path):
    settings = DesktopSettingsStore(tmp_path / "settings.json")
    settings.update({"disabled_model_ids": ["beta"]})
    controlled = SettingsAwareRegistry(registry(tmp_path), settings)

    assert [item.id for item in controlled.enabled()] == ["alpha"]
    assert controlled.enabled_ids() == frozenset({"alpha"})
    assert [item.id for item in controlled.all_models()] == ["alpha", "beta"]
    assert controlled.get("alpha").id == "alpha"
    with pytest.raises(ModelDisabledError, match="disabled"):
        controlled.get("beta")
