#!/usr/bin/env bash
set -euo pipefail

PROVIDER="${MENTAT_PROVIDER:-vast}"
OLLAMA_MODEL="${MENTAT_OLLAMA_MODEL:-kimi-k2.7-code:cloud}"
ROOT_DIR="${MENTAT_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BROKER_PORT="${MENTAT_BROKER_PORT:-18890}"
BROKER_DATA_DIR="${MENTAT_BROKER_DATA_DIR:-${HOME}/.config/mentat/broker}"
STATE_DIR="${MENTAT_STATE_DIR:-${HOME}/.config/mentat/state}"
BROKER_ADMIN_TOKEN_FILE="${STATE_DIR}/broker-admin.token"

if command -v openclaw >/dev/null 2>&1; then
  OPENCLAW=(openclaw)
elif command -v pnpm >/dev/null 2>&1 && [[ -f "${ROOT_DIR}/package.json" ]]; then
  OPENCLAW=(pnpm openclaw)
else
  echo "OpenClaw is not installed and pnpm source execution is unavailable." >&2
  exit 1
fi

resolve_python() {
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)'; then
    printf '%s' python3
  elif command -v python >/dev/null 2>&1 && python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)'; then
    printf '%s' python
  else
    echo "Python 3.11 or newer is required for the Mentat broker." >&2
    exit 1
  fi
}

random_token() {
  local python_bin="$1"
  "${python_bin}" -c 'import secrets; print(secrets.token_urlsafe(32))'
}

broker_ready() {
  local python_bin="$1"
  local client_token="$2"
  "${python_bin}" - "${BROKER_PORT}" "${client_token}" <<'PY' >/dev/null 2>&1
import sys, urllib.request
request = urllib.request.Request(
    f"http://127.0.0.1:{sys.argv[1]}/v1/models",
    headers={"Authorization": f"Bearer {sys.argv[2]}"},
)
try:
    with urllib.request.urlopen(request, timeout=2) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
}

start_broker() {
  local python_bin="$1"
  local client_token="$2"
  local admin_token="$3"
  local api_key="$4"
  local upstream="$5"
  local template_hash="$6"
  if broker_ready "${python_bin}" "${client_token}"; then
    return
  fi
  mkdir -p "${BROKER_DATA_DIR}" "${STATE_DIR}"
  : >"${STATE_DIR}/broker.out.log"
  : >"${STATE_DIR}/broker.error.log"
  env \
    VAST_API_KEY="${api_key}" \
    VAST_TEMPLATE_HASH="${template_hash}" \
    MENTAT_PRIMARY_UPSTREAM_URL="${upstream}" \
    MENTAT_BROKER_DATA_DIR="${BROKER_DATA_DIR}" \
    MENTAT_BROKER_CLIENT_TOKEN="${client_token}" \
    MENTAT_BROKER_ADMIN_TOKEN="${admin_token}" \
    "${python_bin}" "${ROOT_DIR}/scripts/mentat/broker.py" \
      --root "${ROOT_DIR}" \
      --data-dir "${BROKER_DATA_DIR}" \
      --port "${BROKER_PORT}" \
      --parent-pid "$$" \
      >>"${STATE_DIR}/broker.out.log" \
      2>>"${STATE_DIR}/broker.error.log" &
  local broker_pid=$!
  for _ in $(seq 1 60); do
    if broker_ready "${python_bin}" "${client_token}"; then
      echo "Mentat broker ready on port ${BROKER_PORT} (PID ${broker_pid})."
      return
    fi
    if ! kill -0 "${broker_pid}" 2>/dev/null; then
      break
    fi
    sleep 0.5
  done
  tail -n 80 "${STATE_DIR}/broker.error.log" >&2 || true
  echo "The Mentat broker did not become ready." >&2
  exit 1
}

configure_sandbox() {
  local sandbox_json
  sandbox_json='{"mode":"all","backend":"docker","scope":"session","workspaceAccess":"rw","prune":{"idleHours":24,"maxAgeDays":7}}'
  "${OPENCLAW[@]}" config set agents.defaults.sandbox "${sandbox_json}" --strict-json
  "${OPENCLAW[@]}" config set tools.elevated.enabled false --strict-json
  "${OPENCLAW[@]}" config set gateway.bind '"loopback"' --strict-json
}

assert_sandbox_runtime() {
  [[ "${MENTAT_PRODUCTION_MODE:-1}" == "0" ]] && return
  command -v docker >/dev/null 2>&1 || {
    echo "Production mode requires Docker for OpenClaw tool isolation." >&2
    exit 1
  }
  docker info >/dev/null 2>&1 || {
    echo "Docker is installed but not running." >&2
    exit 1
  }
}

configure_vast() {
  [[ -n "${MENTAT_VLLM_BASE_URL:-}" ]] || {
    echo "MENTAT_VLLM_BASE_URL is required as the Kimi endpoint identity." >&2
    exit 1
  }
  [[ -n "${VAST_API_KEY:-}" ]] || {
    echo "VAST_API_KEY is required for broker-only Vast operations." >&2
    exit 1
  }
  command -v node >/dev/null 2>&1 || {
    echo "Node.js is required to generate the OpenClaw provider configuration." >&2
    exit 1
  }

  local python_bin client_token admin_token
  python_bin="$(resolve_python)"
  client_token="${MENTAT_BROKER_CLIENT_TOKEN:-$(random_token "${python_bin}")}"
  admin_token="${MENTAT_BROKER_ADMIN_TOKEN:-$(random_token "${python_bin}")}"
  mkdir -p "${STATE_DIR}"
  umask 077
  printf '%s' "${admin_token}" >"${BROKER_ADMIN_TOKEN_FILE}"
  chmod 600 "${BROKER_ADMIN_TOKEN_FILE}"

  export VLLM_API_KEY="${client_token}"
  export BROKER_BASE_URL="http://127.0.0.1:${BROKER_PORT}/v1"
  provider_json="$(node <<'NODE'
const provider = {
  baseUrl: process.env.BROKER_BASE_URL,
  apiKey: "${VLLM_API_KEY}",
  api: "openai-completions",
  timeoutSeconds: 2100,
  models: [{
    id: "mentat-auto",
    name: "Mentat Automatic Model Broker",
    reasoning: true,
    input: ["text"],
    contextWindow: 262144,
    maxTokens: 16384,
  }],
};
process.stdout.write(JSON.stringify(provider));
NODE
)"

  export MODEL_REF="vllm/mentat-auto"
  model_allowlist="$(node <<'NODE'
process.stdout.write(JSON.stringify({ [process.env.MODEL_REF]: { alias: "Mentat Auto" } }));
NODE
)"
  primary_model="$(node <<'NODE'
process.stdout.write(JSON.stringify(process.env.MODEL_REF));
NODE
)"

  echo "Configuring local Mentat/OpenClaw to use the production model broker."
  "${OPENCLAW[@]}" config set models.providers.vllm "${provider_json}" --strict-json --merge
  "${OPENCLAW[@]}" config set agents.defaults.models "${model_allowlist}" --strict-json --merge
  "${OPENCLAW[@]}" config set agents.defaults.model.primary "${primary_model}" --strict-json
  configure_sandbox
  "${OPENCLAW[@]}" config validate
  "${OPENCLAW[@]}" models status

  if [[ "${MENTAT_CONFIG_ONLY:-0}" == "1" ]]; then
    rm -f "${BROKER_ADMIN_TOKEN_FILE}"
    return
  fi

  assert_sandbox_runtime
  local api_key="${VAST_API_KEY}"
  local upstream="${MENTAT_VLLM_BASE_URL}"
  local template_hash="${VAST_TEMPLATE_HASH:-}"
  start_broker "${python_bin}" "${client_token}" "${admin_token}" "${api_key}" "${upstream}" "${template_hash}"

  # Gateway and tool subprocesses receive only the non-spending broker client token.
  unset VAST_API_KEY VAST_TEMPLATE_HASH MENTAT_PRIMARY_UPSTREAM_URL MENTAT_BROKER_ADMIN_TOKEN MENTAT_BROKER_CLIENT_TOKEN
  export VLLM_API_KEY="${client_token}"
  trap 'rm -f "${BROKER_ADMIN_TOKEN_FILE}"' EXIT INT TERM
  "${OPENCLAW[@]}" gateway --port "${MENTAT_GATEWAY_PORT:-18789}" --verbose
}

launch_ollama_cloud() {
  command -v ollama >/dev/null 2>&1 || {
    echo "Ollama is not installed or is not on PATH." >&2
    exit 1
  }
  if [[ "${MENTAT_HEADLESS:-0}" == "1" ]]; then
    exec ollama launch openclaw --model "${OLLAMA_MODEL}" --yes
  fi
  exec ollama launch openclaw --model "${OLLAMA_MODEL}"
}

case "${PROVIDER}" in
  vast) configure_vast ;;
  ollama-cloud) launch_ollama_cloud ;;
  *)
    echo "Unsupported MENTAT_PROVIDER: ${PROVIDER}" >&2
    exit 1
    ;;
esac
