#!/usr/bin/env python3
"""Regenerates `python/lulu_ads/_generated_widget_bundle.py` from the
checked-in `js/src/generatedWidgetBundle.ts` -- the same compiled,
self-contained widget HTML both the TypeScript and Python packages embed
(see the design doc: "The compiled bundle becomes the single source of
truth both widget.ts and widget.py embed").

Reads `generatedWidgetBundle.ts` rather than `js/widget-src/dist/index.html`
directly on purpose: `dist/` is a gitignored Vite build artifact that
doesn't exist in a fresh clone and would require the Node/Vite toolchain
just to run this script. `generatedWidgetBundle.ts` is already checked
into git, already produced by `export-bundle.mjs` from that same
`dist/index.html`, and already passed that script's guard checks
(placeholder present, no external `<script src>`/`<link href>`, has an
inline `<script>`) -- so reading it here (a) needs only the Python stdlib
and (b) guarantees the Python side is byte-identical to whatever the JS
side actually ships, not a second independent build that could drift.

Usage (whoever changes `js/widget-src/` and regenerates
`generatedWidgetBundle.ts` via `npm run build` there must also run this,
from the repo root, and commit both files together):

    python3 scripts/sync_widget_bundle.py
    # or: scripts/sync-widget-bundle.sh

This script re-applies the same guard checks as `export-bundle.mjs` as a
second line of defense (e.g. if `generatedWidgetBundle.ts` were hand-edited
or corrupted between the two scripts running).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SOURCE_TS = _REPO_ROOT / "js" / "src" / "generatedWidgetBundle.ts"
_DEST_PY = _REPO_ROOT / "python" / "lulu_ads" / "_generated_widget_bundle.py"
_MARKER = "export const WIDGET_BUNDLE_HTML: string = "
_PLACEHOLDER = "__LULU_ADS_OPTS__"


def _extract_html(ts_source: str) -> str:
    idx = ts_source.find(_MARKER)
    if idx == -1:
        raise SystemExit(
            f"sync-widget-bundle: couldn't find {_MARKER!r} in {_SOURCE_TS} -- "
            "has export-bundle.mjs's output format changed? Update _MARKER above."
        )
    literal = ts_source[idx + len(_MARKER):].rstrip("\n")
    if literal.endswith(";"):
        literal = literal[:-1]
    try:
        return json.loads(literal)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"sync-widget-bundle: failed to parse the WIDGET_BUNDLE_HTML string "
            f"literal in {_SOURCE_TS} as JSON: {exc}"
        ) from exc


def _guard(html: str) -> None:
    """Same checks export-bundle.mjs already ran, re-applied here as a
    second line of defense -- see module docstring."""
    if _PLACEHOLDER not in html:
        raise SystemExit(
            f"sync-widget-bundle: {_SOURCE_TS} is missing the {_PLACEHOLDER} "
            "placeholder -- sponsored_widget_html() has nothing to substitute into."
        )
    if "<script" not in html:
        raise SystemExit(
            f"sync-widget-bundle: {_SOURCE_TS} has no inline <script> -- "
            "did the vite build actually run before export-bundle.mjs?"
        )
    if re.search(r"<script[^>]*\ssrc=", html) or re.search(r"<link[^>]*\shref=", html):
        raise SystemExit(
            f"sync-widget-bundle: {_SOURCE_TS} references an external <script src> "
            "or <link href> -- it must be fully self-contained."
        )


def main() -> None:
    if not _SOURCE_TS.exists():
        raise SystemExit(
            f"sync-widget-bundle: {_SOURCE_TS} doesn't exist -- run `npm run build` "
            "in js/widget-src/ first (produces it via export-bundle.mjs), commit it, "
            "then re-run this script."
        )
    ts_source = _SOURCE_TS.read_text(encoding="utf-8")
    html = _extract_html(ts_source)
    _guard(html)

    generated = f'''"""
GENERATED FILE -- do not hand-edit.

Produced by `scripts/sync_widget_bundle.py` from
`js/src/generatedWidgetBundle.ts` (itself produced by `vite build` +
`export-bundle.mjs` in `js/widget-src/` -- one self-contained HTML file,
everything inlined, source of truth documented in
docs/superpowers/specs/2026-07-24-lulu-ads-widget-live-data-design.md).

Regenerate with `scripts/sync-widget-bundle.sh` (or
`python3 scripts/sync_widget_bundle.py`) from the repo root after
`js/src/generatedWidgetBundle.ts` changes, then commit this file alongside
it.

Consumed by `lulu_ads.widget.sponsored_widget_html()`, which substitutes
the `{_PLACEHOLDER}` placeholder token below with a per-call,
HTML-attribute-escaped JSON options blob before returning the final HTML
string.
"""

WIDGET_BUNDLE_HTML: str = {html!r}
'''

    _DEST_PY.write_text(generated, encoding="utf-8")
    print(f"sync-widget-bundle: wrote {_DEST_PY} ({len(html)} bytes of source HTML)")


if __name__ == "__main__":
    sys.exit(main())
