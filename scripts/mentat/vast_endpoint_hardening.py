from __future__ import annotations

import argparse
import json
import os
from typing import Any

import vast_endpoint_production as lifecycle
from vast_http import API_BASE, VastApiError, atomic_write_json, request_json, result_id


def _resource_id(resource: dict[str, Any] | None) -> int | None:
    if not resource or resource.get("id") is None:
        return None
    return int(resource["id"])


def _validate_pair(
    endpoint: dict[str, Any] | None,
    workergroup: dict[str, Any] | None,
) -> None:
    if workergroup and not endpoint:
        raise RuntimeError(
            "Vast contains an orphan workergroup without its endpoint; resolve it manually"
        )
    if not endpoint or not workergroup:
        return
    associated = workergroup.get("endpoint_id")
    if associated is not None and int(associated) != int(endpoint["id"]):
        raise RuntimeError("the named Vast workergroup belongs to a different endpoint")


def _discover(api_key: str, config: dict[str, Any]):
    endpoint, workergroup = lifecycle._existing(api_key, str(config["endpoint_name"]))
    _validate_pair(endpoint, workergroup)
    return endpoint, workergroup


def _recover_created_resource(
    api_key: str,
    config: dict[str, Any],
    expected: str,
    original_error: Exception,
) -> dict[str, Any]:
    endpoint, workergroup = _discover(api_key, config)
    recovered = endpoint if expected == "endpoint" else workergroup
    if recovered:
        return recovered
    raise RuntimeError(
        f"Vast {expected} creation returned an ambiguous result. No exact-name resource "
        "was found during reconciliation; retry the same create command safely."
    ) from original_error


def command_create(args: argparse.Namespace, config: dict[str, Any]) -> None:
    if not args.accept_test_worker_cost:
        raise RuntimeError(
            "create requires --accept-test-worker-cost because Vast may launch a benchmark worker"
        )
    api_key = lifecycle.require_api_key()
    template_hash = args.template_hash or os.getenv("VAST_TEMPLATE_HASH")
    if not template_hash:
        raise RuntimeError("VAST_TEMPLATE_HASH or --template-hash is required")

    endpoint, workergroup = _discover(api_key, config)
    if args.state.exists():
        state = lifecycle.load_json(args.state)
        if state.get("endpoint_name") != config["endpoint_name"]:
            raise RuntimeError("existing state belongs to a different endpoint")
        if endpoint and workergroup:
            if int(state.get("endpoint_id") or 0) != int(endpoint["id"]):
                raise RuntimeError("local state endpoint id does not match Vast")
            if int(state.get("workergroup_id") or 0) != int(workergroup["id"]):
                raise RuntimeError("local state workergroup id does not match Vast")
            print(json.dumps(lifecycle.redact(state), indent=2))
            return
        # The local file is stale. Preserve remote discovery as the source of truth.
        args.state.unlink(missing_ok=True)

    if not endpoint:
        try:
            response = request_json(
                "POST",
                f"{API_BASE}/endptjobs/",
                api_key,
                lifecycle.endpoint_payload(config),
            )
            endpoint_id = result_id(response)
            endpoint = {"id": endpoint_id, "endpoint_name": config["endpoint_name"]}
        except (VastApiError, TimeoutError, OSError) as exc:
            endpoint = _recover_created_resource(api_key, config, "endpoint", exc)
    endpoint_id = int(endpoint["id"])

    if not workergroup:
        try:
            response = request_json(
                "POST",
                f"{API_BASE}/workergroups/",
                api_key,
                lifecycle.workergroup_payload(
                    config,
                    endpoint_id=endpoint_id,
                    template_hash=str(template_hash),
                ),
            )
            workergroup_id = result_id(response)
            workergroup = {
                "id": workergroup_id,
                "endpoint_id": endpoint_id,
                "endpoint_name": config["endpoint_name"],
            }
        except (VastApiError, TimeoutError, OSError) as exc:
            workergroup = _recover_created_resource(api_key, config, "workergroup", exc)
    _validate_pair(endpoint, workergroup)
    workergroup_id = int(workergroup["id"])

    state = lifecycle._state(config, endpoint_id, workergroup_id, str(template_hash))
    atomic_write_json(args.state, state)
    print(json.dumps(lifecycle.redact(state), indent=2))


def install() -> None:
    lifecycle.command_create = command_create
