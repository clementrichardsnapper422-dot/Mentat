import pytest
from mentat_broker.contracts import utc_now
from mentat_broker.release import REQUIREMENTS, ReleaseEvidence, ReleaseEvidenceStore


def test_release_is_blocked_without_retained_external_and_owner_evidence(tmp_path):
    store = ReleaseEvidenceStore(tmp_path / "release.json")
    report = store.report()
    assert report["production_ready"] is False
    assert report["release_blocked"] is True
    with pytest.raises(RuntimeError, match="blocked"):
        store.assert_production_ready()


def test_all_requirements_must_be_explicitly_recorded(tmp_path):
    store = ReleaseEvidenceStore(tmp_path / "release.json")
    for requirement in REQUIREMENTS:
        store.record(
            ReleaseEvidence(
                requirement_id=requirement.requirement_id,
                status="passed",
                observed_at=utc_now(),
                source="test-evidence",
                actor="test",
            )
        )
    assert store.report()["production_ready"] is True
    store.assert_production_ready()


def test_accepted_risk_is_only_gate_passing_for_security(tmp_path):
    store = ReleaseEvidenceStore(tmp_path / "release.json")
    store.record(
        ReleaseEvidence(
            requirement_id="G0_PRIVATE_REPOSITORY",
            status="accepted_risk",
            observed_at=utc_now(),
            source="owner",
            notes="temporary",
        )
    )
    assert store.report()["gates"][0]["requirements"][0]["passed"] is False
