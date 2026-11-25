#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/drivers/sane/version.lock"
PATCH_PATH="$ROOT_DIR/drivers/sane/$PATCH_FILE"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ARCHIVE="$TMP_DIR/$SOURCE_ARCHIVE"
SOURCE_DIR="$TMP_DIR/source"
mkdir -p "$SOURCE_DIR"

printf '%s  %s\n' "$PATCH_SHA256" "$PATCH_PATH" | sha256sum --check
curl --fail --location --retry 3 --output "$ARCHIVE" "$SOURCE_URL"
printf '%s  %s\n' "$SOURCE_SHA256" "$ARCHIVE" | sha256sum --check

tar -xjf "$ARCHIVE" --strip-components=1 -C "$SOURCE_DIR"
patch --dry-run --batch -p1 -d "$SOURCE_DIR" < "$PATCH_PATH"

echo "Pinned SANE source and SCX-4100 patch verified."
