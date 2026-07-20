from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .models import BenchmarkRecord, Decision, ModelSpec, Offer
from .registry import ModelRegistry, RegistryError
from .router import RoutingError, build_decision, classify_task
from .sessions import ApprovalCoordinator, EndpointSessionManager, SessionError
from .store import BrokerStore, utc_now
from .vast import VastError, VastOfferDiscovery


class BrokerApplication:
    def __init__(self, root: Path, registry_path: Path, data_dir: Path):
        self.root = root
        self.registry = ModelRegistry.load(registry_path)
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = BrokerStore(self.data_dir / "broker.sqlite3")
        self.coordinator = ApprovalCoordinator()
        self.sessions = EndpointSessionManager(
            root=root,
            state_dir=self.data_dir / "endpoints",
            registry=self.registry,
            store=self.store,
            coordinator=self.coordinator,
        )
        self.vast = VastOfferDiscovery()
        self._offer_cache: dict[str, tuple[float, list[Offer]]] = {}
        self._offer_lock = threading.Lock()
        self.sessions.start_sweeper()

    def close(self) -> None:
        self.sessions.stop_sweeper()
        self.store.close()

    def offers_for(self, model: ModelSpec, *, refresh: bool = False) -> list[Offer]:
        if model.provider != "vast":
            return []
        now = time.monotonic()
        with self._offer_lock:
            cached = self._offer_cache.get(model.id)
            if cached and not refresh and now - cached[0] < 60:
                return cached[1]
        try:
            offers = self.vast.search(model, self.registry.policy)
        except VastError:
            offers = []
        with self._offer_lock:
            self._offer_cache[model.id] = (now, offers)
        return offers

    def plan(self, payload: dict[str, Any]) -> Decision:
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("prompt is required")
        requirements = classify_task(
            prompt,
            estimated_input_tokens=int(payload.get("estimated_input_tokens") or 0),
            has_images=bool(payload.get("has_images", False)),
            requires_tools=bool(payload.get("requires_tools", True)),
            risk_level=str(payload.get("risk_level") or "normal"),
        )
        offers: dict[str, list[Offer]] = {}
        for model in self.registry.enabled():
            if requirements.task_class in model.task_classes and model.provider == "vast":
                offers[model.id] = self.offers_for(model)
        decision = build_decision(
            prompt=prompt,
            registry=self.registry,
            store=self.store,
            offers_by_model=offers,
            estimated_input_tokens=int(payload.get("estimated_input_tokens") or 0),
            has_images=bool(payload.get("has_images", False)),
            requires_tools=bool(payload.get("requires_tools", True)),
            risk_level=str(payload.get("risk_level") or "normal"),
            max_hourly_usd=(
                float(payload["max_hourly_usd"]) if payload.get("max_hourly_usd") is not None else None
            ),
            max_total_usd=(
                float(payload["max_total_usd"]) if payload.get("max_total_usd") is not None else None
            ),
        )
        if self.sessions.is_approved(decision.selected_model):
            decision.status = "approved"
            decision.reasons.append("An approved reusable session is already active; no new launch approval is needed.")
        self.store.save_decision(decision)
        return decision

    def approve(self, decision_id: str, payload: dict[str, Any]) -> Decision:
        decision = self.store.get_decision(decision_id)
        if not decision:
            raise KeyError("decision not found")
        return self.sessions.approve(
            decision,
            accept_benchmark_cost=bool(payload.get("accept_benchmark_cost", False)),
        )

    def reject(self, decision_id: str) -> Decision:
        decision = self.sessions.reject(decision_id)
        if not decision:
            raise KeyError("decision not found")
        return decision

    def _prompt_from_messages(self, messages: list[dict[str, Any]]) -> tuple[str, bool]:
        text_parts: list[str] = []
        has_images = False
        for message in messages:
            content = message.get("content")
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") in {"image", "image_url", "input_image"}:
                        has_images = True
                    text = item.get("text")
                    if text:
                        text_parts.append(str(text))
        return "\n".join(text_parts).strip(), has_images

    def prepare_chat(self, payload: dict[str, Any]) -> tuple[Decision, ModelSpec, str]:
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise ValueError("messages must be an array")
        prompt, has_images = self._prompt_from_messages(messages)
        tools = payload.get("tools")
        estimated_tokens = max(1, len(prompt) // 4)
        decision = self.plan(
            {
                "prompt": prompt,
                "has_images": has_images,
                "requires_tools": bool(tools),
                "estimated_input_tokens": estimated_tokens,
                "risk_level": payload.get("mentat_risk_level", "normal"),
                "max_hourly_usd": payload.get("mentat_max_hourly_usd"),
                "max_total_usd": payload.get("mentat_max_total_usd"),
            }
        )
        model = self.registry.get(decision.selected_model)
        if decision.status == "pending":
            resolved = self.coordinator.wait_for_terminal(
                self.store,
                decision.id,
                self.registry.policy.approval_timeout_seconds,
            )
            if not resolved or resolved.status in {"pending", "warming"}:
                self.store.update_decision_status(
                    decision.id,
                    "timed_out",
                    error="approval timed out",
                    completed_at=utc_now(),
                )
                raise SessionError(f"compute approval timed out for decision {decision.id}")
            if resolved.status == "rejected":
                raise PermissionError(f"compute decision {decision.id} was rejected")
            if resolved.status == "failed":
                raise SessionError(resolved.error or "endpoint approval failed")
            decision = resolved
        endpoint = self.sessions.wait_until_ready(model)
        return decision, model, endpoint

    def proxy_chat(self, handler: BaseHTTPRequestHandler, payload: dict[str, Any]) -> None:
        started = time.monotonic()
        decision: Decision | None = None
        selected_model: ModelSpec | None = None
        attempted: list[ModelSpec] = []
        last_error: Exception | None = None
        try:
            decision, selected_model, endpoint = self.prepare_chat(payload)
            attempted.append(selected_model)
            candidates = [(selected_model, endpoint)]
            for fallback in self.sessions.ready_fallbacks(selected_model):
                fallback_endpoint = self.sessions.endpoint_url(fallback)
                if fallback_endpoint:
                    candidates.append((fallback, fallback_endpoint))

            for model, base_url in candidates:
                try:
                    self._proxy_to_model(handler, payload, model, base_url, decision, started)
                    return
                except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
                    last_error = exc
                    if model.id != selected_model.id:
                        attempted.append(model)
                    continue
            raise SessionError(f"all approved model endpoints failed: {last_error}")
        except PermissionError as exc:
            self._json_error(handler, HTTPStatus.FORBIDDEN, "mentat_compute_rejected", str(exc), decision)
        except (ValueError, RoutingError) as exc:
            self._json_error(handler, HTTPStatus.BAD_REQUEST, "mentat_routing_error", str(exc), decision)
        except SessionError as exc:
            self._json_error(
                handler,
                HTTPStatus.CONFLICT,
                "mentat_compute_approval_required",
                str(exc),
                decision,
            )
        except Exception as exc:
            self._json_error(handler, HTTPStatus.BAD_GATEWAY, "mentat_proxy_error", str(exc), decision)

    def _proxy_to_model(
        self,
        handler: BaseHTTPRequestHandler,
        payload: dict[str, Any],
        model: ModelSpec,
        base_url: str,
        decision: Decision,
        started: float,
    ) -> None:
        upstream_payload = dict(payload)
        for key in list(upstream_payload):
            if key.startswith("mentat_"):
                upstream_payload.pop(key, None)
        upstream_payload["model"] = model.model_id
        body = json.dumps(upstream_payload).encode("utf-8")
        api_key = os.getenv(model.api_key_env) or os.getenv("VAST_API_KEY") or "EMPTY"
        request = urllib.request.Request(
            base_url.rstrip("/") + "/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json",
            },
        )
        try:
            response = urllib.request.urlopen(
                request,
                timeout=self.registry.policy.endpoint_ready_timeout_seconds,
            )
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                details = exc.read().decode("utf-8", errors="replace")
                raise SessionError(f"upstream rejected the request with HTTP {exc.code}: {details}") from exc
            raise

        content_type = response.headers.get("Content-Type", "application/json")
        handler.send_response(response.status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("X-Mentat-Decision-Id", decision.id)
        handler.send_header("X-Mentat-Model", model.id)
        handler.send_header("Connection", "close")
        handler.end_headers()

        captured = bytearray()
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            handler.wfile.write(chunk)
            handler.wfile.flush()
            if len(captured) < 2_000_000:
                captured.extend(chunk[: 2_000_000 - len(captured)])
        response.close()

        latency_ms = (time.monotonic() - started) * 1000
        self.sessions.touch(model.id)
        self.store.update_decision_status(decision.id, "completed", completed_at=utc_now())
        tokens_per_second = None
        try:
            if "application/json" in content_type:
                parsed = json.loads(captured.decode("utf-8"))
                usage = parsed.get("usage", {})
                completion_tokens = float(usage.get("completion_tokens") or 0)
                if completion_tokens and latency_ms > 0:
                    tokens_per_second = completion_tokens / (latency_ms / 1000)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            pass
        self.store.add_benchmark(
            BenchmarkRecord(
                model_id=model.id,
                task_class=decision.task_class,
                success=True,
                latency_ms=latency_ms,
                tokens_per_second=tokens_per_second,
                hourly_usd=decision.offer.hourly_usd if decision.offer else None,
                total_cost_usd=decision.estimated_cost_usd,
                quality_score=None,
                notes=f"Automatic runtime measurement for decision {decision.id}",
            )
        )

    def _json_error(
        self,
        handler: BaseHTTPRequestHandler,
        status: HTTPStatus,
        error_type: str,
        message: str,
        decision: Decision | None,
    ) -> None:
        payload: dict[str, Any] = {
            "error": {
                "message": message,
                "type": error_type,
            }
        }
        if decision:
            payload["error"]["decision_id"] = decision.id
            payload["error"]["decision"] = decision.as_dict()
        _write_json(handler, status, payload)


def _write_json(handler: BaseHTTPRequestHandler, status: int | HTTPStatus, payload: Any) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(int(status))
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length > 10 * 1024 * 1024:
        raise ValueError("request body is too large")
    raw = handler.rfile.read(length) if length else b"{}"
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("JSON body must be an object")
    return parsed


def _decision_ui() -> bytes:
    html = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mentat Compute Decisions</title>
<style>
:root { color-scheme: dark; font-family: Segoe UI, system-ui, sans-serif; }
body { margin:0; background:#0b0e18; color:#eef0ff; }
header { position:sticky; top:0; padding:18px 22px; background:#11162a; border-bottom:1px solid #252c4a; }
h1 { font-size:20px; margin:0; }
small { color:#9aa5cc; }
main { padding:18px; display:grid; gap:14px; }
.card { background:#141a2f; border:1px solid #293250; border-radius:14px; padding:16px; box-shadow:0 12px 30px #0005; }
.pending { border-color:#8d7cff; }
.row { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; }
.label { color:#9aa5cc; font-size:12px; text-transform:uppercase; letter-spacing:.08em; }
.value { font-size:15px; margin-top:3px; }
.grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:14px 0; }
.reason { color:#c8cee9; margin:5px 0; }
button { border:0; border-radius:9px; padding:10px 14px; cursor:pointer; font-weight:650; }
.approve { background:#8d7cff; color:white; } .reject { background:#2a3048; color:#f3b9c4; }
.actions { display:flex; gap:9px; margin-top:14px; }
.empty { color:#9aa5cc; text-align:center; padding:50px 0; }
.badge { border-radius:99px; padding:4px 9px; font-size:12px; background:#252c48; }
@media(max-width:720px) { .grid { grid-template-columns:1fr; } }
</style>
</head>
<body>
<header><h1>Mentat Compute Decisions</h1><small>Model quality, live GPU price, approval, reuse, and fallback status</small></header>
<main id="list"><div class="empty">Loading decisions…</div></main>
<script>
const list = document.getElementById('list');
function money(value) { return '$' + Number(value || 0).toFixed(2); }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
async function action(id, verb, body={}) {
  const response = await fetch(`/v1/decisions/${id}/${verb}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  if (!response.ok) { const data = await response.json(); alert(data.error?.message || 'Action failed'); }
  await refresh();
}
async function approveDecision(id) {
  const accepted = confirm('Approve this model and GPU plan? This may create or warm paid Vast compute up to the displayed policy caps.');
  if (!accepted) return;
  await action(id, 'approve', {accept_benchmark_cost:true});
}
function render(decision) {
  const offer = decision.offer;
  const pending = decision.status === 'pending';
  const reasons = (decision.reasons || []).map(x => `<div class="reason">• ${escapeHtml(x)}</div>`).join('');
  const offerText = offer ? `${offer.num_gpus}× ${escapeHtml(offer.gpu_name)} · ${money(offer.hourly_usd)}/hr` : 'No live offer — conservative cap estimate';
  return `<section class="card ${pending ? 'pending' : ''}">
    <div class="row"><div><div class="label">Task</div><div class="value">${escapeHtml(decision.prompt_preview)}</div></div><span class="badge">${escapeHtml(decision.status)}</span></div>
    <div class="grid">
      <div><div class="label">Selected model</div><div class="value">${escapeHtml(decision.selected_model)}</div></div>
      <div><div class="label">GPU offer</div><div class="value">${offerText}</div></div>
      <div><div class="label">Estimated cost</div><div class="value">${money(decision.estimated_cost_usd)} · ${decision.estimated_minutes} min</div></div>
      <div><div class="label">Task class</div><div class="value">${escapeHtml(decision.task_class)}</div></div>
      <div><div class="label">Quality</div><div class="value">${Number(decision.quality_score).toFixed(3)} (${escapeHtml(decision.quality_source)})</div></div>
      <div><div class="label">Fallbacks</div><div class="value">${escapeHtml((decision.fallback_chain || []).join(' → ') || 'none')}</div></div>
    </div>
    <div>${reasons}</div>
    ${pending ? `<div class="actions"><button class="approve" onclick="approveDecision('${decision.id}')">Approve compute</button><button class="reject" onclick="action('${decision.id}','reject')">Reject</button></div>` : ''}
  </section>`;
}
async function refresh() {
  try {
    const response = await fetch('/v1/decisions?limit=30');
    const data = await response.json();
    list.innerHTML = data.decisions.length ? data.decisions.map(render).join('') : '<div class="empty">No compute decisions yet.</div>';
  } catch (error) { list.innerHTML = `<div class="empty">Broker unavailable: ${escapeHtml(error)}</div>`; }
}
refresh(); setInterval(refresh, 2000);
</script>
</body></html>"""
    return html.encode("utf-8")


def make_handler(application: BrokerApplication):
    class BrokerHandler(BaseHTTPRequestHandler):
        server_version = "MentatBroker/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("[broker] " + (fmt % args) + "\n")

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            try:
                if parsed.path == "/health":
                    _write_json(
                        self,
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "time": datetime.now(UTC).isoformat(),
                            "vast_configured": application.vast.configured,
                            "registry_models": len(application.registry.all()),
                            "policy": application.registry.policy.__dict__,
                        },
                    )
                elif parsed.path in {"/v1/models", "/v1/registry"}:
                    if parsed.path == "/v1/models":
                        _write_json(
                            self,
                            HTTPStatus.OK,
                            {
                                "object": "list",
                                "data": [
                                    {"id": model.model_id, "object": "model", "owned_by": "mentat"}
                                    for model in application.registry.enabled()
                                ],
                            },
                        )
                    else:
                        _write_json(self, HTTPStatus.OK, application.registry.as_public_dict())
                elif parsed.path == "/v1/decisions":
                    status = query.get("status", [None])[0]
                    limit = int(query.get("limit", ["50"])[0])
                    decisions = application.store.list_decisions(status=status, limit=limit)
                    _write_json(self, HTTPStatus.OK, {"decisions": [item.as_dict() for item in decisions]})
                elif parsed.path.startswith("/v1/decisions/"):
                    decision_id = parsed.path.rsplit("/", 1)[-1]
                    decision = application.store.get_decision(decision_id)
                    if not decision:
                        _write_json(self, HTTPStatus.NOT_FOUND, {"error": {"message": "decision not found"}})
                    else:
                        _write_json(self, HTTPStatus.OK, decision.as_dict())
                elif parsed.path == "/v1/benchmarks":
                    limit = int(query.get("limit", ["100"])[0])
                    _write_json(self, HTTPStatus.OK, {"benchmarks": application.store.list_benchmarks(limit)})
                elif parsed.path == "/v1/sessions":
                    _write_json(self, HTTPStatus.OK, {"sessions": application.store.list_sessions()})
                elif parsed.path == "/v1/offers":
                    model_id = query.get("model", [""])[0]
                    model = application.registry.get(model_id)
                    offers = application.offers_for(model, refresh=True)
                    _write_json(self, HTTPStatus.OK, {"model": model_id, "offers": [item.as_dict() for item in offers]})
                elif parsed.path == "/ui/decisions":
                    body = _decision_ui()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    _write_json(self, HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})
            except (ValueError, RegistryError) as exc:
                _write_json(self, HTTPStatus.BAD_REQUEST, {"error": {"message": str(exc)}})
            except Exception as exc:
                _write_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": {"message": str(exc)}})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            try:
                if parsed.path == "/v1/chat/completions":
                    application.proxy_chat(self, _read_json(self))
                    return
                payload = _read_json(self)
                if parsed.path == "/v1/plan":
                    decision = application.plan(payload)
                    _write_json(self, HTTPStatus.CREATED, decision.as_dict())
                elif re.fullmatch(r"/v1/decisions/[^/]+/approve", parsed.path):
                    decision_id = parsed.path.split("/")[3]
                    decision = application.approve(decision_id, payload)
                    _write_json(self, HTTPStatus.OK, decision.as_dict())
                elif re.fullmatch(r"/v1/decisions/[^/]+/reject", parsed.path):
                    decision_id = parsed.path.split("/")[3]
                    decision = application.reject(decision_id)
                    _write_json(self, HTTPStatus.OK, decision.as_dict())
                elif parsed.path == "/v1/benchmarks":
                    record = BenchmarkRecord(
                        model_id=str(payload["model_id"]),
                        task_class=str(payload["task_class"]),
                        success=bool(payload.get("success", True)),
                        latency_ms=float(payload.get("latency_ms", 0)),
                        tokens_per_second=(
                            float(payload["tokens_per_second"])
                            if payload.get("tokens_per_second") is not None
                            else None
                        ),
                        hourly_usd=(
                            float(payload["hourly_usd"]) if payload.get("hourly_usd") is not None else None
                        ),
                        total_cost_usd=(
                            float(payload["total_cost_usd"])
                            if payload.get("total_cost_usd") is not None
                            else None
                        ),
                        quality_score=(
                            float(payload["quality_score"])
                            if payload.get("quality_score") is not None
                            else None
                        ),
                        notes=(str(payload["notes"]) if payload.get("notes") else None),
                    )
                    if record.quality_score is not None and not 0 <= record.quality_score <= 1:
                        raise ValueError("quality_score must be between 0 and 1")
                    record_id = application.store.add_benchmark(record)
                    _write_json(self, HTTPStatus.CREATED, {"id": record_id, "benchmark": record.as_dict()})
                else:
                    _write_json(self, HTTPStatus.NOT_FOUND, {"error": {"message": "not found"}})
            except KeyError as exc:
                _write_json(self, HTTPStatus.NOT_FOUND, {"error": {"message": str(exc)}})
            except (ValueError, RegistryError, RoutingError, SessionError) as exc:
                _write_json(self, HTTPStatus.BAD_REQUEST, {"error": {"message": str(exc)}})
            except Exception as exc:
                _write_json(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": {"message": str(exc)}})

    return BrokerHandler


def find_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "package.json").exists() and (candidate / "scripts" / "mentat").exists():
            return candidate
    raise RuntimeError("could not locate the Mentat repository root")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mentat model and compute broker")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--parent-pid", type=int, help="exit when the owning Mentat process exits")
    parser.add_argument("--check", action="store_true", help="validate configuration and exit")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.root.resolve() if args.root else find_root(Path(__file__))
    registry_path = args.registry or root / "config" / "model-registry.json"
    default_data = Path(os.getenv("MENTAT_BROKER_DATA_DIR") or Path.home() / ".config" / "mentat" / "broker")
    data_dir = args.data_dir or default_data
    application = BrokerApplication(root=root, registry_path=registry_path, data_dir=data_dir)
    port = args.port or application.registry.policy.port
    if args.check:
        print(json.dumps(application.registry.as_public_dict(), indent=2))
        application.close()
        return 0
    server = ThreadingHTTPServer((args.host, port), make_handler(application))
    if args.parent_pid:
        def monitor_parent() -> None:
            while True:
                try:
                    os.kill(args.parent_pid, 0)
                except OSError:
                    server.shutdown()
                    return
                time.sleep(2)
        threading.Thread(target=monitor_parent, name="mentat-broker-parent", daemon=True).start()
    print(f"Mentat broker listening on http://{args.host}:{port}")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        application.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
