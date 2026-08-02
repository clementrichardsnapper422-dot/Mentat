"""Enforce one public production authority boundary.

The established production router is retained only as a deterministic candidate
proposal adapter.  MentatV1ProductionApplication is the only public production
entry point allowed to accept that proposal, create authority state, authorize
paid provider mutations, or begin inference.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class AuthorityBypassError(RuntimeError):
    """Raised when compatibility code is invoked as a second authority."""


@contextmanager
def candidate_proposal_scope(application: Any) -> Iterator[None]:
    """Allow the compatibility router to propose exactly one route.

    This flag is deliberately instance-local and short-lived.  Calling the
    legacy plan method directly on the production 1.0 application fails closed.
    """

    if getattr(application, "_mentat_candidate_proposal_active", False):
        raise AuthorityBypassError("nested candidate proposal scopes are forbidden")
    application._mentat_candidate_proposal_active = True
    try:
        yield
    finally:
        application._mentat_candidate_proposal_active = False


def install_single_authority_hooks() -> None:
    """Make the 1.0 application the sole public production control plane."""

    from .production import MentatV1ProductionApplication
    from .production_app import ProductionBrokerApplication

    if getattr(ProductionBrokerApplication, "_mentat_single_authority_installed", False):
        return

    legacy_plan = ProductionBrokerApplication.plan
    authoritative_plan = MentatV1ProductionApplication.plan

    def guarded_legacy_plan(self: ProductionBrokerApplication, payload: dict[str, Any]):
        if isinstance(self, MentatV1ProductionApplication) and not getattr(
            self, "_mentat_candidate_proposal_active", False
        ):
            raise AuthorityBypassError(
                "the compatibility router may only propose a route inside the "
                "Mentat 1.0 authority boundary"
            )
        return legacy_plan(self, payload)

    def single_authority_plan(
        self: MentatV1ProductionApplication,
        payload: dict[str, Any],
    ):
        with candidate_proposal_scope(self):
            decision = authoritative_plan(self, payload)
        if decision.metadata.get("authority_owner") != "mentat-v1":
            raise AuthorityBypassError("route escaped without Mentat 1.0 authority ownership")
        execution_id = decision.metadata.get("authority_execution_id")
        if not execution_id or self.v1.executions.get(str(execution_id)) is None:
            raise AuthorityBypassError("route escaped without durable authority execution state")
        return decision

    ProductionBrokerApplication.plan = guarded_legacy_plan  # type: ignore[method-assign]
    MentatV1ProductionApplication.plan = single_authority_plan  # type: ignore[method-assign]
    ProductionBrokerApplication._mentat_single_authority_installed = True  # type: ignore[attr-defined]
