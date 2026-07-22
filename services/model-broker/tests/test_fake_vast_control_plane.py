# ruff: noqa: E402, I001
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "scripts" / "mentat"
TESTING = SCRIPTS / "testing"
if str(TESTING) not in sys.path:
    sys.path.insert(0, str(TESTING))

from fake_vast import start_fake_vast
from mentat_broker.registry import ModelRegistry
from mentat_broker.vast import VastOfferDiscovery

REGISTRY = ROOT / "config" / "model-registry.json"
KIMI_CONFIG = ROOT / "infrastructure" / "vast" / "kimi-k2.7-code" / "endpoint.json"
LIFECYCLE = ROOT / "scripts" / "mentat" / "vast_endpoint.py"


def run_lifecycle(
    state_path: Path,
    api_base: str,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "VAST_API_KEY": "test-vast-key",
            "MENTAT_VAST_API_BASE": api_base,
        }
    )
    return subprocess.run(
        [
            sys.executable,
            str(LIFECYCLE),
            "--config",
            str(KIMI_CONFIG),
            "--state",
            str(state_path),
            *arguments,
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_offer_discovery_uses_the_no_spend_http_marketplace() -> None:
    server, thread = start_fake_vast()
    base = f"http://127.0.0.1:{server.server_address[1]}/api/v0"
    try:
        registry = ModelRegistry.load(REGISTRY)
        model = registry.get("kimi-k2.7-code")
        discovery = VastOfferDiscovery(
            api_key="test-vast-key",
            api_url=base + "/bundles/",
            timeout=2,
            max_attempts=1,
        )
        offers = discovery.search(model, registry.policy)
        assert [offer.id for offer in offers] == [501, 502]
        assert offers[0].hourly_usd == 24
        assert server.state.calls[-1]["path"] == "/api/v0/bundles/"
        assert server.state.calls[-1]["payload"]["type"] == "ondemand"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_endpoint_lifecycle_runs_entirely_against_fake_vast(tmp_path: Path) -> None:
    server, thread = start_fake_vast()
    base = f"http://127.0.0.1:{server.server_address[1]}/api/v0"
    state_path = tmp_path / "kimi-state.json"
    try:
        created = run_lifecycle(
            state_path,
            base,
            "create",
            "--template-hash",
            "fake-template",
            "--accept-test-worker-cost",
        )
        assert created.returncode == 0, created.stderr
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["endpoint_id"] in server.state.endpoints
        assert state["workergroup_id"] in server.state.workergroups
        assert server.state.workergroups[state["workergroup_id"]]["cold_workers"] == 0

        status = run_lifecycle(state_path, base, "status")
        assert status.returncode == 0, status.stderr
        status_payload = json.loads(status.stdout)
        assert status_payload["endpoint"]["id"] == state["endpoint_id"]
        assert status_payload["workergroup"]["id"] == state["workergroup_id"]

        warmed = run_lifecycle(state_path, base, "warm")
        assert warmed.returncode == 0, warmed.stderr
        assert server.state.endpoints[state["endpoint_id"]]["cold_workers"] == 1
        assert server.state.workergroups[state["workergroup_id"]]["cold_workers"] == 1

        cooled = run_lifecycle(state_path, base, "cool")
        assert cooled.returncode == 0, cooled.stderr
        assert server.state.endpoints[state["endpoint_id"]]["cold_workers"] == 0
        assert server.state.workergroups[state["workergroup_id"]]["cold_workers"] == 0

        request = urllib.request.Request(
            base + "/billing/",
            headers={"Authorization": "Bearer test-vast-key"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            billing = json.loads(response.read().decode("utf-8"))
        assert billing["results"][0]["total_usd"] == 0

        destroyed = run_lifecycle(state_path, base, "destroy", "--confirm")
        assert destroyed.returncode == 0, destroyed.stderr
        assert not state_path.exists()
        assert server.state.endpoints == {}
        assert server.state.workergroups == {}
        assert all("console.vast.ai" not in call["path"] for call in server.state.calls)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
