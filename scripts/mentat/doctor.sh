#!/usr/bin/env bash
set -u

ROOT_DIR="${MENTAT_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
CONFIG_DIR="${MENTAT_CONFIG_DIR:-$HOME/.config/mentat}"
ENV_FILE="$CONFIG_DIR/env"
PID_FILE="$CONFIG_DIR/gateway.pid"
INSTALL_CHECK=0
[[ "${1:-}" == "--install-check" ]] && INSTALL_CHECK=1

failures=0
warnings=0

pass() { printf '  [OK]   %s\n' "$*"; }
warn() { printf '  [WARN] %s\n' "$*"; warnings=$((warnings + 1)); }
fail() { printf '  [FAIL] %s\n' "$*"; failures=$((failures + 1)); }

printf 'Mentat doctor\n'
printf 'Repository: %s\n\n' "$ROOT_DIR"

printf 'System\n'
if command -v git >/dev/null 2>&1; then
  pass "Git $(git --version | awk '{print $3}')"
else
  fail "Git is not installed"
fi

if command -v node >/dev/null 2>&1; then
  if node -e '
const [major, minor, patch] = process.versions.node.split(".").map(Number);
const ok =
  (major === 22 && (minor > 22 || (minor === 22 && patch >= 3))) ||
  (major === 24 && (minor > 15 || (minor === 15 && patch >= 0))) ||
  (major === 25 && (minor > 9 || (minor === 9 && patch >= 0)));
process.exit(ok ? 0 : 1);
'; then
    pass "Node.js $(node --version)"
  else
    fail "Unsupported Node.js $(node --version); use 24.15+ (recommended), 22.22.3+, or 25.9+"
  fi
else
  fail "Node.js is not installed"
fi

PNPM_BIN=""
if command -v pnpm >/dev/null 2>&1; then
  PNPM_BIN="$(command -v pnpm)"
elif [[ -x "$HOME/.local/bin/pnpm" ]]; then
  PNPM_BIN="$HOME/.local/bin/pnpm"
fi
if [[ -n "$PNPM_BIN" ]]; then
  pass "pnpm $($PNPM_BIN --version)"
else
  fail "pnpm is not installed; rerun bash install.sh"
fi

if command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    pass "$(python3 --version)"
  else
    fail "Python 3.11+ is required; found $(python3 --version 2>&1)"
  fi
else
  fail "Python 3 is not installed"
fi

printf '\nCheckout\n'
if [[ -f "$ROOT_DIR/package.json" && -f "$ROOT_DIR/openclaw.mjs" ]]; then
  pass "Mentat source checkout found"
else
  fail "This does not look like a complete Mentat checkout"
fi

if [[ -d "$ROOT_DIR/node_modules" ]]; then
  pass "Node dependencies installed"
else
  fail "node_modules is missing; rerun bash install.sh"
fi

if [[ -x "$HOME/.local/bin/mentat" ]]; then
  pass "mentat command installed at $HOME/.local/bin/mentat"
else
  warn "mentat command is not installed in ~/.local/bin"
fi

if [[ ":$PATH:" == *":$HOME/.local/bin:"* ]]; then
  pass "~/.local/bin is on PATH"
else
  warn "~/.local/bin is not on this terminal's PATH; open a new terminal"
fi

printf '\nConfiguration\n'
if [[ -f "$ENV_FILE" ]]; then
  pass "Local configuration found at $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a

  provider="${MENTAT_PROVIDER:-}"
  if [[ -n "$provider" ]]; then
    pass "Provider: $provider"
  else
    warn "No inference provider selected; run mentat setup"
  fi

  case "$provider" in
    vast)
      [[ -n "${MENTAT_VLLM_BASE_URL:-}" ]] && pass "Vast endpoint URL configured" || fail "MENTAT_VLLM_BASE_URL is missing"
      [[ -n "${VAST_API_KEY:-}" ]] && pass "Vast credential configured" || fail "Vast credential is missing"
      [[ -n "${MENTAT_MODEL_ID:-}" ]] && pass "Model: $MENTAT_MODEL_ID" || fail "MENTAT_MODEL_ID is missing"
      [[ -n "${VAST_TEMPLATE_HASH:-}" ]] && pass "Vast template hash configured" || warn "Vast template hash is optional until endpoint creation"
      ;;
    ollama-cloud)
      if command -v ollama >/dev/null 2>&1; then
        pass "Ollama installed"
      else
        fail "Ollama Cloud is selected but Ollama is not installed"
      fi
      ;;
    "") ;;
    *) fail "Unknown provider: $provider" ;;
  esac
else
  if [[ "$INSTALL_CHECK" -eq 1 ]]; then
    warn "Setup has not been completed; run mentat setup"
  else
    fail "Local configuration is missing; run mentat setup"
  fi
fi

printf '\nRuntime\n'
if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    pass "Gateway wrapper process is running (PID $pid)"
  else
    warn "Stale Gateway PID file found"
  fi
else
  warn "Gateway is not currently running"
fi

if [[ "$failures" -eq 0 ]]; then
  printf '\nResult: healthy'
  [[ "$warnings" -gt 0 ]] && printf ' with %d warning(s)' "$warnings"
  printf '.\n'
  exit 0
fi

printf '\nResult: %d failure(s), %d warning(s).\n' "$failures" "$warnings"
exit 1
