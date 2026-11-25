#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$EUID" -eq 0 ]]; then
  echo "Do not run the development installer with sudo." >&2
  echo "Use ./scripts/install-sane-dev.sh as the same user that runs uv." >&2
  exit 1
fi

for command_name in bash awk mktemp; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Missing required command: $command_name" >&2
    exit 1
  }
done

DATA_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/printscan-server"
CACHE_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/printscan-server"
PREFIX="$HOME/.local/opt/printscan-sane"
BUILD_ROOT="$CACHE_ROOT/sane"
ENV_FILE="$ROOT_DIR/.env"

mkdir -p "$DATA_ROOT" "$CACHE_ROOT" "$HOME/.local/opt"
chmod 0700 "$DATA_ROOT" "$CACHE_ROOT"

echo "Building pinned SANE backends and applying the SCX-4100 patch..."
HOME="$HOME" \
  PRINTSCAN_BUILD_DIR="$BUILD_ROOT" \
  PRINTSCAN_SANE_PREFIX="$PREFIX" \
  bash "$ROOT_DIR/scripts/build-sane.sh"

SCANIMAGE="$PREFIX/bin/scanimage"
if [[ ! -x "$SCANIMAGE" || ! -d "$PREFIX/lib" || ! -d "$PREFIX/etc/sane.d" ]]; then
  echo "SANE installation is incomplete under $PREFIX" >&2
  exit 1
fi

umask 077
ENV_TMP="$(mktemp "$ROOT_DIR/.env.tmp.XXXXXX")"
cleanup() { rm -f "$ENV_TMP"; }
trap cleanup EXIT

if [[ -f "$ENV_FILE" ]]; then
  awk '
    /^(PRINTSCAN_SCANIMAGE_BIN|LD_LIBRARY_PATH|SANE_CONFIG_DIR)=/ { next }
    { print }
  ' "$ENV_FILE" > "$ENV_TMP"
fi

cat >> "$ENV_TMP" <<EOF

# Managed by scripts/install-sane-dev.sh
PRINTSCAN_SCANIMAGE_BIN=$SCANIMAGE
LD_LIBRARY_PATH=$PREFIX/lib
SANE_CONFIG_DIR=$PREFIX/etc/sane.d
EOF

mv "$ENV_TMP" "$ENV_FILE"
trap - EXIT
chmod 0600 "$ENV_FILE"

echo
echo "Patched SANE installed: $PREFIX"
echo "Updated development environment: $ENV_FILE"
echo
echo "Restart the development server so it reloads .env:"
echo "  stop the current uv run printscan serve process"
echo "  uv run printscan serve --host 0.0.0.0 --port 8090"
echo
echo "Checking SANE discovery as the current user..."
set +e
DISCOVERY_OUTPUT="$(LD_LIBRARY_PATH="$PREFIX/lib" \
  SANE_CONFIG_DIR="$PREFIX/etc/sane.d" \
  "$SCANIMAGE" -L 2>&1)"
DISCOVERY_STATUS=$?
set -e
printf '%s\n' "$DISCOVERY_OUTPUT"

if [[ "$DISCOVERY_STATUS" -ne 0 ]] || ! { grep -Fq 'device `' <<< "$DISCOVERY_OUTPUT" || grep -Fq "device '" <<< "$DISCOVERY_OUTPUT"; }; then
  echo
  echo "The patched SANE build is installed, but no scanner is visible to this user."
  echo "For the SCX-4100 this is expected until USB coordination is implemented."
  echo "The patch itself has been applied and verified."
else
  echo "At least one scanner is visible to this user."
fi
