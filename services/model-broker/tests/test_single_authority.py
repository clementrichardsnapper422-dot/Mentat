from __future__ import annotations

from types import SimpleNamespace

import pytest
from mentat_broker.single_authority import AuthorityBypassError, candidate_proposal_scope


def test_candidate_proposal_scope_is_short_lived() -> None:
    application = SimpleNamespace()

    assert not getattr(application, "_mentat_candidate_proposal_active", False)
    with candidate_proposal_scope(application):
        assert application._mentat_candidate_proposal_active is True
    assert application._mentat_candidate_proposal_active is False


def test_candidate_proposal_scope_clears_after_failure() -> None:
    application = SimpleNamespace()

    with (
        pytest.raises(RuntimeError, match="proposal failed"),
        candidate_proposal_scope(application),
    ):
        raise RuntimeError("proposal failed")

    assert application._mentat_candidate_proposal_active is False


def test_nested_candidate_proposal_is_rejected() -> None:
    application = SimpleNamespace()

    with (
        candidate_proposal_scope(application),
        pytest.raises(AuthorityBypassError, match="nested"),
        candidate_proposal_scope(application),
    ):
        pass
