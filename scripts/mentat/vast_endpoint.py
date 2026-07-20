#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

API_BASE = "https://console.vast.ai/api/v0"
DEFAULT_CONFIG = Path("infrastructure/vast/kimi-k2.7-code/endpoint.json")
DEFAULT_STATE = Path.home() / ".config" / "mentat" / "vast-endpoint.json"


class VastApiError(RuntimeError):
    """Raised when the Vast API returns a non-successful response."""


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
    required = ("endpoint_name", "model_id", "openai_base_url", "endpoint", "workergroup", "policy")
    missing = [key for key in required if key not in config]
    if missing:
        raise RuntimeError(f"missing configuration keys: {', '.join(missing)}")

    endpoint = config["endpoint"]
    workergroup = config["workergroup"]
    policy = config["policy"]
    if not isinstance(endpoint, dict) or not isinstance(workergroup, dict) or not isinstance(policy, dict):
        raise RuntimeError("endpoint, workergroup, and policy must be JSON objects")

    max_workers = int(endpoint.get("max_workers", 0))
    if max_workers != 1 or int(workergroup.get("max_workers", 0)) != 1:
        raise RuntimeError("the initial Mentat Kimi profile must allow exactly one worker cluster")

    hourly_cap = float(policy.get("max_hourly_usd", 0))
    if hourly_cap <= 0:
        raise RuntimeError("policy.max_hourly_usd must be greater than zero")
    search_params = str(workergroup.get("search_params", ""))
    if f"dph_total<={hourly_cap:g}" not in search_params:
        raise RuntimeError("workergroup.search_params must enforce policy.max_hourly_usd")


def require_api_key() -> str:
    api_key = os.getenv("VAST_API_KEY")
    if not api_key:
        raise RuntimeError("VAST_API_KEY is required")
    return api_key


def request_json(
    method: str,
    url: str,
    api_key: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 90,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise VastApiError(f"Vast API {exc.code} for {method} {url}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise VastApiError(f"Vast API connection failed for {method} {url}: {exc.reason}") from exc
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise VastApiError(f"Vast API returned a non-object response for {method} {url}")
    return parsed


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


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def load_state(path: Path) -> dict[str, Any]:
    return load_json(path)


def build_launch_args(config: dict[str, Any]) -> str:
    workergroup = config["workergroup"]
    model_id = str(config["model_id"])
    vllm_args = str(workergroup["vllm_args"])
    env_value = f"-e MODEL_NAME={model_id} -e VLLM_ARGS={shlex.quote(vllm_args)}"
    disk_gb = int(workergroup["disk_gb"])
    return f"--env {shlex.quote(env_value)} --disk {disk_gb}"


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
    payload = {
        key: value
        for key, value in source.items()
        if key not in {"vllm_args", "disk_gb"}
    }
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


def command_create(args: argparse.Namespace, config: dict[str, Any]) -> None:
    api_key = require_api_key()
    template_hash = args.template_hash or os.getenv("VAST_TEMPLATE_HASH")
    if not template_hash:
        raise RuntimeError("VAST_TEMPLATE_HASH or --template-hash is required")

    endpoint = request_json("POST", f"{API_BASE}/endptjobs/", api_key, endpoint_payload(config))
    endpoint_id = int(endpoint["result"])
    try:
        workergroup = request_json(
            "POST",
            f"{API_BASE}/workergroups/",
            api_key,
            workergroup_payload(config, endpoint_id=endpoint_id, template_hash=template_hash),
        )
        workergroup_id = int(workergroup["id"])
    except Exception:
        request_json("DELETE", f"{API_BASE}/endptjobs/{endpoint_id}/", api_key)
        raise

    state = {
        "endpoint_name": config["endpoint_name"],
        "endpoint_id": endpoint_id,
        "workergroup_id": workergroup_id,
        "template_hash": template_hash,
        "openai_base_url": config["openai_base_url"],
        "created_at": datetime.now(UTC).isoformat(),
    }
    save_state(args.state, state)
    print(json.dumps(redact(state), indent=2))


def command_status(args: argparse.Namespace, config: dict[str, Any]) -> None:
    api_key = require_api_key()
    endpoints = request_json("GET", f"{API_BASE}/endptjobs/", api_key)
    workergroups = request_json("GET", f"{API_BASE}/workergroups/", api_key)
    name = config["endpoint_name"]
    result = {
        "endpoints": [item for item in endpoints.get("results", []) if item.get("endpoint_name") == name],
        "workergroups": [
            item for item in workergroups.get("results", []) if item.get("endpoint_name") == name
        ],
    }
    print(json.dumps(redact(result), indent=2))


def set_temperature(args: argparse.Namespace, config: dict[str, Any], cold_workers: int) -> None:
    api_key = require_api_key()
    state = load_state(args.state)
    endpoint_id = int(state["endpoint_id"])
    workergroup_id = int(state["workergroup_id"])
    template_hash = str(state["template_hash"])

    request_json(
        "PUT",
        f"{API_BASE}/endptjobs/{endpoint_id}/",
        api_key,
        endpoint_payload(config, cold_workers=cold_workers),
    )
    request_json(
        "PUT",
        f"{API_BASE}/workergroups/{workergroup_id}/",
        api_key,
        workergroup_payload(
            config,
            endpoint_id=endpoint_id,
            template_hash=template_hash,
            cold_workers=cold_workers,
        ),
    )
    state["cold_workers"] = cold_workers
    state["updated_at"] = datetime.now(UTC).isoformat()
    save_state(args.state, state)
    print("warm" if cold_workers else "cool")


def command_destroy(args: argparse.Namespace, config: dict[str, Any]) -> None:
    del config
    if not args.confirm:
        raise RuntimeError("destroy requires --confirm")
    api_key = require_api_key()
    state = load_state(args.state)
    workergroup_id = int(state["workergroup_id"])
    endpoint_id = int(state["endpoint_id"])
    request_json("DELETE", f"{API_BASE}/workergroups/{workergroup_id}/", api_key)
    request_json("DELETE", f"{API_BASE}/endptjobs/{endpoint_id}/", api_key)
    args.state.unlink(missing_ok=True)
    print("destroyed")


def command_test(args: argparse.Namespace, config: dict[str, Any]) -> None:
    api_key = require_api_key()
    base_url = str(config["openai_base_url"]).rstrip("/")
    payload = {
        "model": config["model_id"],
        "messages": [{"role": "user", "content": args.prompt}],
        "max_tokens": args.max_tokens,
        "temperature": 1.0,
        "top_p": 0.95,
        "stream": False,
    }
    response = request_json(
        "POST",
        f"{base_url}/chat/completions",
        api_key,
        payload,
        timeout=args.timeout,
    )
    print(json.dumps(redact(response), indent=2))


def command_print_env(args: argparse.Namespace, config: dict[str, Any]) -> None:
    del args
    print("export MENTAT_PROVIDER=vast")
    print(f"export MENTAT_VLLM_BASE_URL={shlex.quote(str(config['openai_base_url']))}")
    print(f"export MENTAT_MODEL_ID={shlex.quote(str(config['model_id']))}")
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
        "within_policy": args.hourly_price <= cap and args.hours <= float(policy["max_session_hours"]),
    }
    print(json.dumps(result, indent=2))
    if not result["within_policy"]:
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Mentat's Vast Kimi endpoint")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="create endpoint and workergroup")
    create.add_argument("--template-hash")

    subparsers.add_parser("status", help="show endpoint and workergroup state")
    subparsers.add_parser("warm", help="keep one Kimi worker cluster warm")
    subparsers.add_parser("cool", help="allow the endpoint to scale to zero")

    destroy = subparsers.add_parser("destroy", help="delete endpoint and workergroup")
    destroy.add_argument("--confirm", action="store_true")

    test = subparsers.add_parser("test", help="send a direct chat-completion request")
    test.add_argument("--prompt", default="Reply with exactly: Mentat online")
    test.add_argument("--max-tokens", type=int, default=64)
    test.add_argument("--timeout", type=int, default=1800)

    subparsers.add_parser("print-env", help="print local Mentat connection commands")

    estimate = subparsers.add_parser("estimate", help="estimate a planned session cost")
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
