from datetime import UTC, datetime, timedelta

import pytest

from mentat_broker.contracts import ApprovalLease, BackendKind, RangeEstimate


def test_range_estimate_requires_ordered_non_negative_values():
    assert RangeEstimate(1, 2, 3, "USD").expected == 2
    with pytest.raises(ValueError):
        RangeEstimate(2, 1, 3, "USD")
    with pytest.raises(ValueError):
        RangeEstimate(-1, 1, 3, "USD")


def test_approval_lease_is_signed_scoped_and_expires():
    secret = b"a" * 32
    now = datetime.now(UTC)
    lease = ApprovalLease.issue(
        secret,
        decision_id="decision-1",
        subject="local-admin",
        expires_at=(now + timedelta(minutes=5)).isoformat(),
        allowed_backend=BackendKind.VAST_SERVERLESS,
        allowed_model_id="kimi",
        maximum_hourly_usd=2,
        maximum_total_usd=4,
    )
    lease.verify(
        secret,
        now=now,
        subject="local-admin",
        backend=BackendKind.VAST_SERVERLESS,
        model_id="kimi",
    )
    with pytest.raises(PermissionError, match="subject"):
        lease.verify(secret, now=now, subject="model")
    with pytest.raises(PermissionError, match="expired"):
        lease.verify(secret, now=now + timedelta(hours=1))
    tampered = ApprovalLease(**{**lease.__dict__, "maximum_total_usd": 100})
    with pytest.raises(PermissionError, match="signature"):
        tampered.verify(secret, now=now)
