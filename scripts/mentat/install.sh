#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_DIR="${MENTAT_CONFIG_DIR:-$HOME/.config/mentat}"
BIN_DIR="${MENTAT_BIN_DIR:-$HOME/.local/bin}"
PNPM_VERSION="11.2.2"
SKIP_DEPS=0
SKIP_UI=0
UPDATE_PATH=1

usage() {
  cat <<'EOF'
Install Mentat from this source checkout.

Usage:
  bash install.sh [options]

Options:
  --skip-deps   Do not run pnpm install
  --skip-ui     Do not build the local Control UI
  --no-path     Do not add ~/.local/bin to your shell PATH
  -h, --help    Show this help
EOF
}

for arg in "$@"; do
  case "$arg" in
    --skip-deps) SKIP_DEPS=1 ;;
    --skip-ui) SKIP_UI=1 ;;
    --no-path) UPDATE_PATH=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

say() { printf '\n==> %s\n' "$*"; }
fail() { printf 'Mentat install error: %s\n' "$*" >&2; exit 1; }

case "$(uname -s)" in
  Darwin|Linux) ;;
  *) fail "This installer supports macOS, Linux, and Windows through WSL2." ;;
esac

command -v git >/dev/null 2>&1 || fail "Git is required."
command -v node >/dev/null 2>&1 || fail "Node.js is required. Install Node 24.15 or newer, then rerun this installer."
command -v npm >/dev/null 2>&1 || fail "npm is required with Node.js."
command -v python3 >/dev/null 2>&1 || fail "Python 3.11 or newer is required for Vast endpoint commands."

if ! node -e '
const [major, minor, patch] = process.versions.node.split(".").map(Number);
const ok =
  (major === 22 && (minor > 22 || (minor === 22 && patch >= 3))) ||
  (major === 24 && (minor > 15 || (minor === 15 && patch >= 0))) ||
  (major === 25 && (minor > 9 || (minor === 9 && patch >= 0)));
process.exit(ok ? 0 : 1);
'; then
  fail "Unsupported Node.js $(node --version). Use Node 24.15+ (recommended), 22.22.3+, or 25.9+."
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  fail "Python 3.11 or newer is required. Found $(python3 --version 2>&1)."
fi

mkdir -p "$BIN_DIR" "$CONFIG_DIR"
export PATH="$BIN_DIR:$PATH"

say "Preparing pnpm $PNPM_VERSION"
if command -v corepack >/dev/null 2>&1; then
  corepack enable >/dev/null 2>&1 || true
  corepack prepare "pnpm@$PNPM_VERSION" --activate >/dev/null 2>&1 || true
fi
if ! command -v pnpm >/dev/null 2>&1; then
  npm install --global --prefix "$HOME/.local" "pnpm@$PNPM_VERSION"
fi
command -v pnpm >/dev/null 2>&1 || fail "pnpm could not be installed into $BIN_DIR."

if [[ "$SKIP_DEPS" -eq 0 ]]; then
  say "Installing Mentat dependencies"
  (cd "$ROOT_DIR" && pnpm install)
fi

if [[ "$SKIP_UI" -eq 0 ]]; then
  say "Building the local Control UI"
  (cd "$ROOT_DIR" && pnpm ui:build)
fi

if [[ ! -f "$CONFIG_DIR/env" ]]; then
  cp "$ROOT_DIR/config/mentat.env.example" "$CONFIG_DIR/env"
fi
chmod 700 "$CONFIG_DIR"
chmod 600 "$CONFIG_DIR/env"

say "Installing the mentat command"
printf '#!/usr/bin/env bash\nexport MENTAT_HOME=%q\nexec bash "$MENTAT_HOME/scripts/mentat/mentat.sh" "$@"\n' \
  "$ROOT_DIR" > "$BIN_DIR/mentat"
chmod 755 "$BIN_DIR/mentat"

SHELL_RC=""
case "${SHELL:-}" in
  */zsh) SHELL_RC="$HOME/.zshrc" ;;
  */bash) SHELL_RC="$HOME/.bashrc" ;;
  *)
    if [[ "$(uname -s)" == "Darwin" ]]; then
      SHELL_RC="$HOME/.zshrc"
    else
      SHELL_RC="$HOME/.bashrc"
    fi
    ;;
esac

if [[ "$UPDATE_PATH" -eq 1 ]] && ! grep -Fq '# Mentat CLI' "$SHELL_RC" 2>/dev/null; then
  {
    printf '\n# Mentat CLI\n'
    printf 'export PATH="$HOME/.local/bin:$PATH"\n'
  } >> "$SHELL_RC"
fi

say "Checking the installation"
bash "$ROOT_DIR/scripts/mentat/doctor.sh" --install-check || true

cat <<EOF

Mentat is installed. 🧠

Next:
  1. Open a new terminal, or run: export PATH="$BIN_DIR:\$PATH"
  2. Run: mentat setup
  3. Run: mentat start
  4. Run: mentat chat

Local secrets and settings are stored in:
  $CONFIG_DIR/env

Useful commands:
  mentat doctor
  mentat help
EOF
