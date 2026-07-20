#!/usr/bin/env bash
set -euo pipefail

MODEL="${MENTAT_MODEL:-kimi-k2.7-code:cloud}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed or is not on PATH." >&2
  echo "Install Ollama, run 'ollama signin', and try again." >&2
  exit 1
fi

echo "Launching Mentat/OpenClaw with model: ${MODEL}"

if [[ "${MENTAT_HEADLESS:-0}" == "1" ]]; then
  exec ollama launch openclaw --model "${MODEL}" --yes "$@"
fi

exec ollama launch openclaw --model "${MODEL}" "$@"
