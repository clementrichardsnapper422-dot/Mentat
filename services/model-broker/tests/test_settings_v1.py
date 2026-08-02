import pytest
from mentat_broker.runtime import MentatV1Runtime
from mentat_broker.settings import DesktopSettingsStore
from mentat_broker.spend import BudgetPolicy


def test_invalid_preview_never_changes_persisted_settings(tmp_path):
    store = DesktopSettingsStore(tmp_path / "settings.json")
    original = store.load()
    with pytest.raises(ValueError, match="remote inference"):
        store.preview_update(
            {
                "privacy_mode": "local_first",
                "remote_inference_enabled": True,
            }
        )
    assert store.load() == original


def test_setup_requires_absolute_workspace_and_valid_budget_hierarchy(tmp_path):
    store = DesktopSettingsStore(tmp_path / "settings.json")
    with pytest.raises(ValueError, match="absolute"):
        store.preview_complete_setup({"workspace": "relative/workspace"})
    with pytest.raises(ValueError, match="daily"):
        store.preview_update(
            {
                "budgets": {
                    "maximum_session_usd": 20,
                    "maximum_daily_usd": 10,
                }
            }
        )


def test_runtime_rejects_preferences_above_immutable_registry_policy(tmp_path):
    runtime = MentatV1Runtime(
        tmp_path / "runtime",
        budget_policy=BudgetPolicy(
            maximum_hourly_usd=10,
            maximum_session_usd=20,
            maximum_daily_usd=30,
            maximum_monthly_usd=120,
            maximum_retry_usd=4,
            maximum_fallback_usd=8,
            maximum_exploration_usd=2,
        ),
    )
    try:
        before = runtime.settings.load()
        with pytest.raises(ValueError, match="immutable registry policy"):
            runtime.update_settings({"budgets": {"maximum_hourly_usd": 11}})
        assert runtime.settings.load() == before
    finally:
        runtime.close()


def test_completed_setup_drives_analysis_and_creates_workspace(tmp_path):
    runtime = MentatV1Runtime(tmp_path / "runtime")
    workspace = (tmp_path / "workspace").resolve()
    try:
        settings = runtime.complete_setup(
            {
                "workspace": str(workspace),
                "routing_mode": "economy",
                "privacy_mode": "local_first",
                "remote_inference_enabled": False,
                "budgets": {"maximum_session_usd": 2},
            }
        )
        assert settings["setup_completed"] is True
        assert workspace.is_dir()
        requirements = runtime.analyze_task("Fix this code bug")
        assert requirements["routing_mode"] == "economy"
        assert requirements["maximum_total_cost_usd"] == 2
    finally:
        runtime.close()
