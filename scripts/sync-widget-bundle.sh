#!/usr/bin/env bash
# Regenerates python/lulu_ads/_generated_widget_bundle.py from the
# checked-in js/src/generatedWidgetBundle.ts, so both published packages
# (lulu-ads on npm, lulu-ads on PyPI) embed byte-identical compiled widget
# HTML -- see scripts/sync_widget_bundle.py's module docstring for the
# full mechanics and why it reads generatedWidgetBundle.ts rather than the
# gitignored js/widget-src/dist/index.html directly.
#
# Run this after regenerating js/src/generatedWidgetBundle.ts (i.e. after
# `npm run build` in js/widget-src/, whenever widget-src/'s source
# changes), then commit both files together. Needs only python3 -- no
# Node/Vite toolchain required to run this step itself.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/sync_widget_bundle.py
