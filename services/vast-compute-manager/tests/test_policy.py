from pathlib import Path

import pytest

from app.policy import PolicyViolation, approve_request
from app.settings import Settings


def settings() -> Settings:
    return Settings(
        vast_api_key=None,
        manager_token=None,
        max_hourly_usd=0.50,
        max_total_usd=1.00,
        max_active_instances=1,
        max_disk_gb=80,
        max_ttl_minutes=30,
        database_path=Path("test.sqlite3"),
        watchdog_interval_seconds=30,
    )


def test_approves_request_inside_all_limits() -> None:
    approved = approve_request(
        settings=settings(),
        requested_max_hourly_usd=0.40,
        disk_gb=40,
        ttl_minutes=15,
        active_instances=0,
    )

    assert approved.max_hourly_usd == 0.40
    assert approved.estimated_max_cost_usd == 0.10


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"requested_max_hourly_usd": 0.60}, "hourly cap"),
        ({"disk_gb": 100}, "disk"),
        ({"ttl_minutes": 60}, "lifetime"),
        ({"active_instances": 1}, "active instance"),
    ],
)
def test_rejects_requests_outside_policy(kwargs: dict, message: str) -> None:
    request = {
        "requested_max_hourly_usd": 0.40,
        "disk_gb": 40,
        "ttl_minutes": 15,
        "active_instances": 0,
    }
    request.update(kwargs)

    with pytest.raises(PolicyViolation, match=message):
        approve_request(settings=settings(), **request)
