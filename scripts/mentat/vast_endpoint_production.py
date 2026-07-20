#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vast_http import API_BASE, VastApiError, atomic_write_json, request_json, result_id, results

DEFAULT_CONFIG = Path("infrastructure/vast/kimi-k2.7-code/endpoint.json")
DEFAULT_STATE = Path.home() / ".config" / "mentat" / "vast-endpoint.json"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"configuration file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object in {path}")
    return value


def validate_config(config: dict[str, Any]) -> None:
    required = (
        "endpoint_name",
        "model_id",
        "openai_base_url",
        "endpoint",
        "workergroup",
        "policy",
    )
    missing = [key for key in required if key not in config]
    if missing:
        raise RuntimeError(f"missing configuration keys: {', '.join(missing)}")
    name = str(config["endpoint_name"])
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", name):
        raise RuntimeError("endpoint_name must be a lowercase DNS-style name")
    if not str(config["model_id"]).strip():
        raise RuntimeError("model_id is required")
    url = str(config["openai_base_url"])
    if not url.startswith("https://openai.vast.ai/") or not url.rstrip("/").endswith("/v1"):
        raise RuntimeError("openai_base_url must be a Vast HTTPS /v1 endpoint")

    endpoint = config["endpoint"]
    workergroup = config["workergroup"]
    policy = config["policy"]
    if not isinstance(endpoint, dict) or not isinstance(workergroup, dict) or not isinstance(policy, dict):
        raise RuntimeError("endpoint, workergroup, and policy must be JSON objects")
    if int(endpoint.get("max_workers", 0)) != 1 or int(workergroup.get("max_workers", 0)) != 1:
        raise RuntimeError("Mentat endpoint profiles must allow exactly one worker cluster")
    if int(workergroup.get("test_workers", 0)) not in {0, 1}:
        raise RuntimeError("test_workers must be zero or one")
    if int(workergroup.get("disk_gb", 0)) <= 0:
        raise RuntimeError("workergroup.disk_gb must be positive")
    if not str(workergroup.get("vllm_args") or "").strip():
        raise RuntimeError("workergroup.vllm_args is required")
    hourly_cap = float(policy.get("max_hourly_usd", 0))
    if hourly_cap <= 0:
        raise RuntimeError("policy.max_hourly_usd must be greater than zero")
    search_params = str(workergroup.get("search_params", ""))
    match = re.search(r"dph_total\s*<=\s*([0-9.]+)", search_params)
    if not match or float(match.group(1)) > hourly_cap + 1e-9:
        raise RuntimeError("workergroup.search_params must enforce policy.max_hourly_usd")
    if "verified=true" not in search_params or "rentable=true" not in search_params:
        raise RuntimeError("workergroup.search_params must require verified rentable workers")


def require_api_key() -> str:
    value = os.getenv("VAST_API_KEY")
    if not value:
        raise RuntimeError("VAST_API_KEY is required")
    return value


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            result[key] = "***" if any(word in lowered for word in ("key", "token", "secret")) else redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def build_launch_args(config: dict[str, Any]) -> str:
    workergroup = config["workergroup"]
    model_id = str(config["model_id"])
    vllm_args = str(workergroup["vllm_args"])
    env_value = f"-e MODEL_NAME={model_id} -e VLLM_ARGS={shlex.quote(vllm_args)}"
    return f"--env {shlex.quote(env_value)} --disk {int(workergroup['disk_gb'])}"


def endpoint_payload(config: dict[str, Any], *, cold_workers: int | None = None) -> dict[str, Any]:
    payload = dict(config["endpoint"])
    payload["endpoint_name"] = config["endpoint_name"]
    if cold_workers is not None:
        payload["cold_workers"] = cold_workers
    return payload


def workergroup_payload(
    config: dict[str, Any],
    *,
    endpoint_id: int,
    template_hash: str,
    cold_workers: int | None = None,
) -> dict[str, Any]:
    source = config["workergroup"]
    payload = {key: value for key, value in source.items() if key not in {"vllm_args", "disk_gb"}}
    payload.update(
        {
            "endpoint_name": config["endpoint_name"],
            "endpoint_id": endpoint_id,
            "template_hash": template_hash,
            "launch_args": build_launch_args(config),
        }
    )
    if cold_workers is not None:
        payload["cold_workers"] = cold_workers
    return payload


def _named_resources(api_key: str, resource: str, name: str) -> list[dict[str, Any]]:
    payload = request_json("GET", f"{API_BASE}/{resource}/", api_key)
    matches = [item for item in results(payload) if str(item.get("endpoint_name") or item.get("name") or "") == name]
    if len(matches) > 1:
        raise RuntimeError(f"multiple Vast {resource} resources use endpoint name {name}")
    return matches


def _existing(api_key: str, name: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    endpoints = _named_resources(api_key, "endptjobs", name)
    workergroups = _named_resources(api_key, "workergroups", name)
    return (endpoints[0] if endpoints else None, workergroups[0] if workergroups else None)


def _state(config: dict[str, Any], endpoint_id: int, workergroup_id: int, template_hash: str) -> dict[str, Any]:
    return {
        "endpoint_name": config["endpoint_name"],
        "model_id": config["model_id"],
        "endpoint_id": endpoint_id,
        "workergroup_id": workergroup_id,
        "template_hash": template_hash,
        "openai_base_url": config["openai_base_url"],
        "cold_workers": 0,
        "created_at": datetime.now(UTC).isoformat(),
    }


def command_create(args: argparse.Namespace, config: dict[str, Any]) -> None:
    if not args.accept_test_worker_cost:
        raise RuntimeError("create requires --accept-test-worker-cost because Vast may launch a benchmark worker")
    api_key = require_api_key()
    template_hash = args.template_hash or os.getenv("VAST_TEMPLATE_HASH")
    if not template_hash:
        raise RuntimeError("VAST_TEMPLATE_HASH or --template-hash is required")
    if args.state.exists():
        state = load_json(args.state)
        if state.get("endpoint_name") != config["endpoint_name"]:
            raise RuntimeError("existing state belongs to a different endpoint")
        print(json.dumps(redact(state), indent=2))
        return

    endpoint, workergroup = _existing(api_key, str(config["endpoint_name"]))
    if workergroup and not endpoint:
        raise RuntimeError("Vast contains an orphan workergroup without its endpoint; resolve it manually")
    created_endpoint = False
    if endpoint:
        endpoint_id = int(endpoint["id"])
    else:
        response = request_json("POST", f"{API_BASE}/endptjobs/", api_key, endpoint_payload(config))
        endpoint_id = result_id(response)
        created_endpoint = True

    try:
        if workergroup:
            workergroup_id = int(workergroup["id"])
        else:
            response = request_json(
                "POST",
                f"{API_BASE}/workergroups/",
                api_key,
                workergroup_payload(config, endpoint_id=endpoint_id, template_hash=template_hash),
            )
            workergroup_id = result_id(response)
    except Exception:
        if created_endpoint:
            request_json(
                "DELETE",
                f"{API_BASE}/endptjobs/{endpoint_id}/",
                api_key,
                allow_not_found=True,
            )
        raise

    state = _state(config, endpoint_id, workergroup_id, template_hash)
    atomic_write_json(args.state, state)
    print(json.dumps(redact(state), indent=2))


def command_status(args: argparse.Namespace, config: dict[str, Any]) -> None:
    api_key = require_api_key()
    endpoint, workergroup = _existing(api_key, str(config["endpoint_name"]))
    state = load_json(args.state) if args.state.exists() else None
    print(json.dumps(redact({"state": state, "endpoint": endpoint, "workergroup": workergroup}), indent=2))


def set_temperature(args: argparse.Namespace, config: dict[str, Any], cold_workers: int) -> None:
    api_key = require_api_key()
    state = load_json(args.state)
    if state.get("endpoint_name") != config["endpoint_name"]:
        raise RuntimeError("endpoint state does not match the selected profile")
    endpoint_id = int(state["endpoint_id"])
    workergroup_id = int(state["workergroup_id"])
    template_hash = str(state["template_hash"])

    if cold_workers:
        request_json(
            "PUT",
            f"{API_BASE}/workergroups/{workergroup_id}/",
            api_key,
            workergroup_payload(
                config,
                endpoint_id=endpoint_id,
                template_hash=template_hash,
                cold_workers=1,
            ),
        )
        try:
            request_json(
                "PUT",
                f"{API_BASE}/endptjobs/{endpoint_id}/",
                api_key,
                endpoint_payload(config, cold_workers=1),
            )
        except Exception:
            request_json(
                "PUT",
                f"{API_BASE}/workergroups/{workergroup_id}/",
                api_key,
                workergroup_payload(
                    config,
                    endpoint_id=endpoint_id,
                    template_hash=template_hash,
                    cold_workers=0,
                ),
            )
            raise
    else:
        request_json(
            "PUT",
            f"{API_BASE}/endptjobs/{endpoint_id}/",
            api_key,
            endpoint_payload(config, cold_workers=0),
            allow_not_found=True,
        )
        request_json(
            "PUT",
            f"{API_BASE}/workergroups/{workergroup_id}/",
            api_key,
            workergroup_payload(
                config,
                endpoint_id=endpoint_id,
                template_hash=template_hash,
                cold_workers=0,
            ),
            allow_not_found=True,
        )
    state["cold_workers"] = cold_workers
    state["updated_at"] = datetime.now(UTC).isoformat()
    atomic_write_json(args.state, state)
    print("warm" if cold_workers else "cool")


def command_destroy(args: argparse.Namespace, config: dict[str, Any]) -> None:
    if not args.confirm:
        raise RuntimeError("destroy requires --confirm")
    api_key = require_api_key()
    if args.state.exists():
        state = load_json(args.state)
        workergroup_id = int(state["workergroup_id"])
        endpoint_id = int(state["endpoint_id"])
    else:
        endpoint, workergroup = _existing(api_key, str(config["endpoint_name"]))
        workergroup_id = int(workergroup["id"]) if workergroup else 0
        endpoint_id = int(endpoint["id"]) if endpoint else 0
    if workergroup_id:
        request_json(
            "DELETE",
            f"{API_BASE}/workergroups/{workergroup_id}/",
            api_key,
            allow_not_found=True,
        )
    if endpoint_id:
        request_json(
            "DELETE",
            f"{API_BASE}/endptjobs/{endpoint_id}/",
            api_key,
            allow_not_found=True,
        )
    args.state.unlink(missing_ok=True)
    print("destroyed")


def command_test(args: argparse.Namespace, config: dict[str, Any]) -> None:
    api_key = require_api_key()
    payload = {
        "model": config["model_id"],
        "messages": [{"role": "user", "content": args.prompt}],
        "max_tokens": args.max_tokens,
        "temperature": 0,
        "stream": False,
    }
    response = request_json(
        "POST",
        str(config["openai_base_url"]).rstrip("/") + "/chat/completions",
        api_key,
        payload,
        timeout=args.timeout,
        attempts=1,
    )
    print(json.dumps(redact(response), indent=2))


def command_print_env(args: argparse.Namespace, config: dict[str, Any]) -> None:
    del args
    print("export MENTAT_PROVIDER=vast")
    print(f"export MENTAT_VLLM_BASE_URL={shlex.quote(str(config['openai_base_url']))}")
    print('# export VAST_API_KEY="set-this-locally"')
    print("bash scripts/mentat/launch.sh")


def command_estimate(args: argparse.Namespace, config: dict[str, Any]) -> None:
    policy = config["policy"]
    cap = float(policy["max_hourly_usd"])
    estimated = args.hourly_price * args.hours
    result = {
        "hourly_price_usd": round(args.hourly_price, 2),
        "hours": round(args.hours, 2),
        "estimated_cost_usd": round(estimated, 2),
        "hourly_cap_usd": cap,
        "within_policy": args.hourly_price <= cap
        and args.hours <= float(policy["max_session_hours"]),
    }
    print(json.dumps(result, indent=2))
    if not result["within_policy"]:
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage a guarded Mentat Vast endpoint")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="idempotently create endpoint and workergroup")
    create.add_argument("--template-hash")
    create.add_argument("--accept-test-worker-cost", action="store_true")
    commands.add_parser("status", help="show endpoint, workergroup, and local state")
    commands.add_parser("warm", help="keep one approved worker cluster warm")
    commands.add_parser("cool", help="allow the endpoint to scale to zero")
    destroy = commands.add_parser("destroy", help="idempotently delete endpoint and workergroup")
    destroy.add_argument("--confirm", action="store_true")
    test = commands.add_parser("test", help="send a direct chat-completion request")
    test.add_argument("--prompt", default="Reply with exactly: Mentat online")
    test.add_argument("--max-tokens", type=int, default=64)
    test.add_argument("--timeout", type=int, default=1800)
    commands.add_parser("print-env", help="print local Mentat connection commands")
    estimate = commands.add_parser("estimate", help="estimate a planned session cost")
    estimate.add_argument("--hourly-price", type=float, required=True)
    estimate.add_argument("--hours", type=float, required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        config = load_json(args.config)
        validate_config(config)
        commands = {
            "create": command_create,
            "status": command_status,
            "warm": lambda namespace, cfg: set_temperature(namespace, cfg, 1),
            "cool": lambda namespace, cfg: set_temperature(namespace, cfg, 0),
            "destroy": command_destroy,
            "test": command_test,
            "print-env": command_print_env,
            "estimate": command_estimate,
        }
        commands[args.command](args, config)
    except (RuntimeError, VastApiError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
