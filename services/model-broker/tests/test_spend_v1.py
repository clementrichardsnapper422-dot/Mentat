from datetime import UTC, datetime, timedelta

import pytest

from mentat_broker.contracts import BackendKind
from mentat_broker.spend import BudgetPolicy, SpendError, SpendGovernor


def governor(tmp_path):
    return SpendGovernor(
        tmp_path / "spend.sqlite3",
        signing_secret=b"s" * 32,
        policy=BudgetPolicy(
            maximum_hourly_usd=10,
            maximum_session_usd=20,
            maximum_daily_usd=25,
            maximum_monthly_usd=100,
            maximum_retry_usd=2,
            maximum_fallback_usd=5,
            maximum_exploration_usd=1,
        ),
    )


def lease(instance, decision="d1", total=10):
    return instance.issue_lease(
        decision_id=decision,
        subject="admin",
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        backend=BackendKind.VAST_SERVERLESS,
        model_id="kimi",
        maximum_hourly_usd=5,
        maximum_total_usd=total,
    )


def test_reservation_is_idempotent_and_one_session_is_enforced(tmp_path):
    instance = governor(tmp_path)
    authority = lease(instance)
    first = instance.reserve(
        authority,
        reservation_id="r1",
        subject="admin",
        backend=BackendKind.VAST_SERVERLESS,
        model_id="kimi",
        hourly_usd=3,
        worst_case_usd=8,
    )
    again = instance.reserve(
        authority,
        reservation_id="r1",
        subject="admin",
        backend=BackendKind.VAST_SERVERLESS,
        model_id="kimi",
        hourly_usd=3,
        worst_case_usd=8,
    )
    assert first == again
    with pytest.raises(SpendError, match="another paid session"):
        instance.reserve(
            lease(instance, "d2"),
            reservation_id="r2",
            subject="admin",
            backend=BackendKind.VAST_SERVERLESS,
            model_id="kimi",
            hourly_usd=3,
            worst_case_usd=4,
        )
    instance.release("r1", reason="cancelled")
    assert instance.get("r1").state == "released"


def test_overspend_fails_closed_and_activates_kill_switch(tmp_path):
    instance = governor(tmp_path)
    instance.reserve(
        lease(instance),
        reservation_id="r1",
        subject="admin",
        backend=BackendKind.VAST_SERVERLESS,
        model_id="kimi",
        hourly_usd=3,
        worst_case_usd=4,
    )
    with pytest.raises(SpendError, match="kill switch"):
        instance.commit("r1", 5)
    assert instance.kill_switch_enabled()
    assert instance.get("r1").state == "reconciling"
    with pytest.raises(SpendError, match="kill switch"):
        lease(instance, "d2")


def test_dedicated_exploration_cap(tmp_path):
    instance = governor(tmp_path)
    with pytest.raises(SpendError, match="exploration"):
        instance.reserve(
            lease(instance),
            reservation_id="exp",
            subject="admin",
            backend=BackendKind.VAST_SERVERLESS,
            model_id="kimi",
            hourly_usd=1,
            worst_case_usd=2,
            kind="exploration",
        )
