#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="printscan"
DATA_DIR="/var/lib/printscan-server"
PREFIX="$DATA_DIR/sane"
BUILD_DIR="$DATA_DIR/sane-build"
ENV_DIR="/etc/printscan-server"
ENV_FILE="$ENV_DIR/sane.env"
UNIT_FILE="/etc/systemd/system/printscan-server.service"

if [[ "$EUID" -ne 0 ]]; then
  echo "Run this installer with sudo: sudo $0" >&2
  exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "Service account '$SERVICE_USER' does not exist." >&2
  echo "Install PrintScan Server first; see docs/deployment.md." >&2
  exit 1
fi

if [[ ! -f "$ROOT_DIR/drivers/sane/version.lock" || ! -x "$ROOT_DIR/scripts/build-sane.sh" ]]; then
  echo "PrintScan Server source tree is incomplete: $ROOT_DIR" >&2
  exit 1
fi

for command_name in runuser install systemctl; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Missing required command: $command_name" >&2
    exit 1
  }
done

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$DATA_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$BUILD_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$PREFIX"

echo "Building pinned SANE backends and applying the SCX-4100 patch..."
runuser -u "$SERVICE_USER" -- env \
  HOME="$DATA_DIR" \
  PRINTSCAN_BUILD_DIR="$BUILD_DIR" \
  PRINTSCAN_SANE_PREFIX="$PREFIX" \
  bash "$ROOT_DIR/scripts/build-sane.sh"

SCANIMAGE="$PREFIX/bin/scanimage"
if [[ ! -x "$SCANIMAGE" || ! -d "$PREFIX/lib" || ! -d "$PREFIX/etc/sane.d" ]]; then
  echo "SANE installation is incomplete under $PREFIX" >&2
  exit 1
fi

install -d -m 0750 "$ENV_DIR"
ENV_TMP="$(mktemp "$ENV_DIR/sane.env.XXXXXX")"
trap 'rm -f "$ENV_TMP"' EXIT
cat > "$ENV_TMP" <<EOF
PRINTSCAN_SCANIMAGE_BIN=$SCANIMAGE
LD_LIBRARY_PATH=$PREFIX/lib
SANE_CONFIG_DIR=$PREFIX/etc/sane.d
EOF
chown root:"$SERVICE_USER" "$ENV_TMP"
chmod 0640 "$ENV_TMP"
mv "$ENV_TMP" "$ENV_FILE"
trap - EXIT

if [[ -f "$ROOT_DIR/deploy/printscan-server.service" ]]; then
  install -m 0644 "$ROOT_DIR/deploy/printscan-server.service" "$UNIT_FILE"
  systemctl daemon-reload
fi

echo
echo "Patched SANE installed: $PREFIX"
echo "The PrintScan service will use the custom scanimage and SANE libraries."

if systemctl is-active --quiet printscan-server.service; then
  systemctl restart printscan-server.service
  echo "PrintScan Server restarted."
else
  echo "PrintScan Server is not active; restart it after completing deployment."
fi

echo
echo "Checking scanner discovery as the service account..."
set +e
DISCOVERY_OUTPUT="$(runuser -u "$SERVICE_USER" -- env \
  LD_LIBRARY_PATH="$PREFIX/lib" \
  SANE_CONFIG_DIR="$PREFIX/etc/sane.d" \
  "$SCANIMAGE" -L 2>&1)"
DISCOVERY_STATUS=$?
set -e
printf '%s\n' "$DISCOVERY_OUTPUT"
if [[ "$DISCOVERY_STATUS" -ne 0 ]] || ! grep -Fq "device '" <<< "$DISCOVERY_OUTPUT"; then
  echo
  echo "SANE was installed, but no scanner was confirmed for the service account."
  echo "For the SCX-4100 this is expected until its USB broker is installed."
  echo "The patched backend is installed; USB access is a separate permission/coordination step."
else
  echo "At least one scanner is visible to the service account."
fi
