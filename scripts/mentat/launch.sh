#!/usr/bin/env bash
set -euo pipefail

PROVIDER="${MENTAT_PROVIDER:-vast}"
OLLAMA_MODEL="${MENTAT_OLLAMA_MODEL:-kimi-k2.7-code:cloud}"
ROOT_DIR="${MENTAT_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BROKER_PORT="${MENTAT_BROKER_PORT:-18890}"
BROKER_DATA_DIR="${MENTAT_BROKER_DATA_DIR:-${HOME}/.config/mentat/broker}"
STATE_DIR="${MENTAT_STATE_DIR:-${HOME}/.config/mentat/state}"

if command -v openclaw >/dev/null 2>&1; then
  OPENCLAW=(openclaw)
elif command -v pnpm >/dev/null 2>&1 && [[ -f package.json ]]; then
  OPENCLAW=(pnpm openclaw)
else
  echo "OpenClaw is not installed and pnpm source execution is unavailable." >&2
  echo "Install dependencies in the Mentat repository or install OpenClaw globally." >&2
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

broker_ready() {
  local python_bin="$1"
  "${python_bin}" - "${BROKER_PORT}" <<'PY' >/dev/null 2>&1
import sys, urllib.request
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/health", timeout=1) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
}

start_broker() {
  local python_bin
  python_bin="$(resolve_python)"
  if broker_ready "${python_bin}"; then
    return
  fi
  mkdir -p "${BROKER_DATA_DIR}" "${STATE_DIR}"
  : >"${STATE_DIR}/broker.out.log"
  : >"${STATE_DIR}/broker.error.log"
  "${python_bin}" "${ROOT_DIR}/scripts/mentat/broker.py" \
    --root "${ROOT_DIR}" \
    --data-dir "${BROKER_DATA_DIR}" \
    --port "${BROKER_PORT}" \
    --parent-pid "$$" \
    >>"${STATE_DIR}/broker.out.log" \
    2>>"${STATE_DIR}/broker.error.log" &
  local broker_pid=$!
  for _ in $(seq 1 40); do
    if broker_ready "${python_bin}"; then
      echo "Mentat broker ready on port ${BROKER_PORT} (PID ${broker_pid})."
      return
    fi
    if ! kill -0 "${broker_pid}" 2>/dev/null; then
      break
    fi
    sleep 0.5
  done
  tail -n 50 "${STATE_DIR}/broker.error.log" >&2 || true
  echo "The Mentat broker did not become ready." >&2
  exit 1
}

configure_vast() {
  if [[ -z "${MENTAT_VLLM_BASE_URL:-}" ]]; then
    cat >&2 <<'EOF'
MENTAT_VLLM_BASE_URL is required as the primary Kimi upstream.

Use the OpenAI-compatible /v1 base URL for your Vast endpoint.
EOF
    exit 1
  fi

  if [[ -z "${VAST_API_KEY:-}" ]]; then
    echo "VAST_API_KEY is required for Vast inference and offer discovery." >&2
    exit 1
  fi

  if ! command -v node >/dev/null 2>&1; then
    echo "Node.js is required to generate the OpenClaw provider configuration." >&2
    exit 1
  fi

  export MENTAT_PRIMARY_UPSTREAM_URL="${MENTAT_VLLM_BASE_URL}"
  export MENTAT_BROKER_DATA_DIR="${BROKER_DATA_DIR}"
  export VLLM_API_KEY="mentat-local-broker"
  export BROKER_BASE_URL="http://127.0.0.1:${BROKER_PORT}/v1"

  provider_json="$(node <<'NODE'
const provider = {
  baseUrl: process.env.BROKER_BASE_URL,
  apiKey: "${VLLM_API_KEY}",
  api: "openai-completions",
  timeoutSeconds: 2100,
  models: [
    {
      id: "mentat-auto",
      name: "Mentat Automatic Model Broker",
      reasoning: true,
      input: ["text", "image"],
      contextWindow: 262144,
      maxTokens: 16384,
    },
  ],
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

  echo "Configuring local Mentat/OpenClaw to use the model and compute broker."
  echo "Broker: ${BROKER_BASE_URL}"
  echo "Primary upstream: ${MENTAT_PRIMARY_UPSTREAM_URL}"

  "${OPENCLAW[@]}" config set models.providers.vllm "${provider_json}" --strict-json --merge
  "${OPENCLAW[@]}" config set agents.defaults.models "${model_allowlist}" --strict-json --merge
  "${OPENCLAW[@]}" config set agents.defaults.model.primary "${primary_model}" --strict-json
  "${OPENCLAW[@]}" config validate
  "${OPENCLAW[@]}" models status

  if [[ "${MENTAT_CONFIG_ONLY:-0}" == "1" ]]; then
    return
  fi

  start_broker
  exec "${OPENCLAW[@]}" gateway --port "${MENTAT_GATEWAY_PORT:-18789}" --verbose
}

launch_ollama_cloud() {
  if ! command -v ollama >/dev/null 2>&1; then
    echo "Ollama is not installed or is not on PATH." >&2
    echo "Install Ollama, run 'ollama signin', and try again." >&2
    exit 1
  fi

  echo "Launching the Ollama Cloud fallback model: ${OLLAMA_MODEL}"

  if [[ "${MENTAT_HEADLESS:-0}" == "1" ]]; then
    exec ollama launch openclaw --model "${OLLAMA_MODEL}" --yes
  fi

  exec ollama launch openclaw --model "${OLLAMA_MODEL}"
}

case "${PROVIDER}" in
  vast)
    configure_vast
    ;;
  ollama-cloud)
    launch_ollama_cloud
    ;;
  *)
    echo "Unsupported MENTAT_PROVIDER: ${PROVIDER}" >&2
    echo "Supported providers: vast, ollama-cloud" >&2
    exit 1
    ;;
esac
