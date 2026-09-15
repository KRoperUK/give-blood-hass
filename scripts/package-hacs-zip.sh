#!/usr/bin/env bash
# Build the release asset HACS downloads.
#
# hacs.json sets `zip_release` with `filename: nhs_give_blood.zip`, so HACS
# expects a zip whose *contents* are the integration files at the top level — not
# a nested custom_components/nhs_give_blood/ path. Getting that wrong installs an
# integration HACS cannot find.
set -euo pipefail

COMPONENT_DIR="custom_components/nhs_give_blood"
OUTPUT="nhs_give_blood.zip"

if [[ ! -d "$COMPONENT_DIR" ]]; then
  echo "error: $COMPONENT_DIR not found; run from the repository root" >&2
  exit 1
fi

rm -f "$OUTPUT"

# -x excludes caches that would otherwise ship to every user.
(
  cd "$COMPONENT_DIR"
  zip -r -q "../../$OUTPUT" . \
    -x '__pycache__/*' \
    -x '*.pyc' \
    -x '.DS_Store'
)

# Captured once rather than piped twice: `grep -q` exits on first match and
# SIGPIPEs `unzip`, which under `set -o pipefail` fails the whole pipeline and
# would make this check report a false failure.
listing="$(unzip -l "$OUTPUT")"

echo "built $OUTPUT:"
echo "$listing"

# manifest.json must be at the archive root for HACS to read it.
if ! grep -q ' manifest.json$' <<<"$listing"; then
  echo "error: manifest.json is not at the root of $OUTPUT" >&2
  exit 1
fi

echo "OK: manifest.json is at the archive root"
