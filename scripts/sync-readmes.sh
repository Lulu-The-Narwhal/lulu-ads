#!/usr/bin/env bash
# Copy the root README into both package directories.
#
# Both packages publish a README to their registry, and neither is the root
# file. js/ had a prepublishOnly that did this; python/ had nothing, so
# python/README.md silently fell four releases behind and PyPI rendered a
# Skybridge description that had been false since 0.9.15. Run this before
# publishing either package -- both package manifests now call it.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cp "$root/README.md" "$root/js/README.md"
cp "$root/README.md" "$root/python/README.md"
echo "synced README.md -> js/ and python/"
