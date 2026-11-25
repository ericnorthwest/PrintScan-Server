#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="$ROOT_DIR/drivers/sane/version.lock"
source "$LOCK_FILE"

BUILD_ROOT="${PRINTSCAN_BUILD_DIR:-$ROOT_DIR/.build/sane}"
PREFIX="${PRINTSCAN_SANE_PREFIX:-$HOME/opt/printscan-sane}"
ARCHIVE="$BUILD_ROOT/$SOURCE_ARCHIVE"
PATCH_PATH="$ROOT_DIR/drivers/sane/$PATCH_FILE"
SOURCE_DIR="$BUILD_ROOT/source"
JOBS="${PRINTSCAN_BUILD_JOBS:-$(nproc)}"

for command_name in curl sha256sum tar patch make; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Missing required command: $command_name" >&2
    exit 1
  }
done

[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || {
  echo "PRINTSCAN_BUILD_JOBS must be a positive integer" >&2
  exit 1
}

mkdir -p "$BUILD_ROOT"
if [[ ! -f "$ARCHIVE" ]] || ! printf '%s  %s\n' "$SOURCE_SHA256" "$ARCHIVE" | sha256sum --check --status; then
  echo "Downloading pinned SANE source archive..."
  rm -f "$ARCHIVE"
  curl --fail --location --retry 3 --output "$ARCHIVE.tmp" "$SOURCE_URL"
  printf '%s  %s\n' "$SOURCE_SHA256" "$ARCHIVE.tmp" | sha256sum --check
  mv "$ARCHIVE.tmp" "$ARCHIVE"
fi

printf '%s  %s\n' "$PATCH_SHA256" "$PATCH_PATH" | sha256sum --check

WORK_DIR="$(mktemp -d "$BUILD_ROOT/work.XXXXXX")"
cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT
mkdir -p "$SOURCE_DIR"
tar -xjf "$ARCHIVE" --strip-components=1 -C "$SOURCE_DIR"

if [[ ! -x "$SOURCE_DIR/configure" ]]; then
  if [[ -x "$SOURCE_DIR/autogen.sh" ]]; then
    (cd "$SOURCE_DIR" && ./autogen.sh)
  else
    echo "Neither configure nor autogen.sh exists in the source archive" >&2
    exit 1
  fi
fi

patch --dry-run --batch -p1 -d "$SOURCE_DIR" < "$PATCH_PATH"
patch --batch -p1 -d "$SOURCE_DIR" < "$PATCH_PATH"

mkdir -p "$PREFIX"
(
  cd "$SOURCE_DIR"
  BACKENDS="$BUILD_BACKENDS" ./configure \
    --prefix="$PREFIX" \
    --libdir="$PREFIX/lib" \
    --sysconfdir="$PREFIX/etc" \
    --localstatedir="$PREFIX/var" \
    --with-usb \
    --disable-preload
  make -j"$JOBS"
  make install
)

echo
echo "SANE $SANE_VERSION installed in: $PREFIX"
echo "Backends requested: $BUILD_BACKENDS"
echo "This script does not configure USB permissions or detach usblp."
