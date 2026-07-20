#!/usr/bin/env bash
set -euo pipefail

PROVIDER="${MENTAT_PROVIDER:-vast}"
MODEL_ID="${MENTAT_MODEL_ID:-moonshotai/Kimi-K2.7-Code}"
OLLAMA_MODEL="${MENTAT_OLLAMA_MODEL:-kimi-k2.7-code:cloud}"

if command -v openclaw >/dev/null 2>&1; then
  OPENCLAW=(openclaw)
elif command -v pnpm >/dev/null 2>&1 && [[ -f package.json ]]; then
  OPENCLAW=(pnpm openclaw)
else
  echo "OpenClaw is not installed and pnpm source execution is unavailable." >&2
  echo "Install dependencies in the Mentat repository or install OpenClaw globally." >&2
  exit 1
fi

configure_vast() {
  if [[ -z "${MENTAT_VLLM_BASE_URL:-}" ]]; then
    cat >&2 <<'EOF'
MENTAT_VLLM_BASE_URL is required for Vast inference.

For a Vast Serverless OpenAI-compatible endpoint, use the endpoint URL supplied by Vast.
Example:
  export MENTAT_VLLM_BASE_URL="https://openai.vast.ai/<ENDPOINT_NAME>"
EOF
    exit 1
  fi

  if [[ -z "${VAST_API_KEY:-}" ]]; then
    echo "VAST_API_KEY is required for Vast inference." >&2
    exit 1
  fi

  echo "Configuring local Mentat/OpenClaw to use Vast-hosted vLLM."
  echo "Model: ${MODEL_ID}"
  echo "Endpoint: ${MENTAT_VLLM_BASE_URL}"

  "${OPENCLAW[@]}" onboard \
    --non-interactive \
    --mode local \
    --auth-choice vllm \
    --custom-base-url "${MENTAT_VLLM_BASE_URL}" \
    --custom-api-key "${VAST_API_KEY}" \
    --custom-model-id "${MODEL_ID}"

  "${OPENCLAW[@]}" models set "vllm/${MODEL_ID}"
  "${OPENCLAW[@]}" models status

  if [[ "${MENTAT_CONFIG_ONLY:-0}" == "1" ]]; then
    return
  fi

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
