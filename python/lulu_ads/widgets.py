"""Result-widget template gallery for FastMCP servers (MCP Apps UI).

Most publishers shouldn't design UI. This module ships four predefined,
host-native-quality result widgets -- the publisher picks a template and
maps their tool's ``structuredContent`` fields into it; the frame, design
tokens, and the disclosed SPONSORED strip are fixed by the SDK::

    from lulu_ads.widgets import register_result_widget

    register_result_widget(
        mcp, "get_weather",
        template="stat-card",
        mapping={
            "eyebrow": "location.name",
            "value": {"path": "temperature_c", "suffix": "°"},
            "condition": "conditions",
            "chips": [{"path": "humidity_pct", "prefix": "\U0001f4a7 ", "suffix": "%"}],
            "atmosphere": "weather_code",
        },
        endpoint_url="https://my-server.example.com/mcp",
    )

Templates: ``stat-card`` (big value + chips + optional condition-keyed
atmospheric background), ``table-card`` (headed rows, mono numerics,
best-row highlight, optional per-row ``rowLink`` -- a dot-path resolving to
a URL, e.g. a booking/checkout link, opened the same way the sponsored
strip's own link is), ``notice-card`` (verdict glyph + detail rows),
``carousel-card`` (3-8 swipeable option cards). ``body_html=`` is the
custom escape hatch: static HTML composed ONLY of the ``.lw-*`` primitives
(``.lw-eyebrow .lw-value .lw-sublabel .lw-chip .lw-row .lw-glyph``),
rendered inside the same frame.

Non-negotiables baked into the frame (the body cannot remove or restyle
them):

* the SPONSORED strip, pinned at the bottom, rendered only when the live
  ``structuredContent.sponsored`` exists -- orange rail left, then logo
  tile -> ad text -> CTA -> "via Lulu Ads". ``sponsored.logo_url`` renders
  in the tile with an automatic letter-tile fallback (brand initial,
  hash-derived background) on absence or load error, so a blocked or dead
  logo never leaves a hole;
* the transparent canvas (``color-scheme: light dark`` -- the 0.7.4 fix;
  without it Chromium paints an opaque white backdrop on dark hosts);
* the host bridge: ``ui/notifications/initialized`` on load,
  ``ui/notifications/size-changed`` after render, data via the host's
  ``ui/notifications/tool-result`` message, clicks out via
  ``ui/open-link``. Same proven-in-Claude contract as widget.py's
  sponsored card and weather-mcp's original bespoke widget.

Mapping entries are either a dot-path string (``"location.name"``) or
``{"path": ..., "prefix": ..., "suffix": ...}``. Numbers are rounded for
display; every runtime value is inserted with ``textContent`` (never
``innerHTML``), so hostile tool output cannot break out of the markup.

Port of js/src/widgets.ts -- keep both in sync.
"""
from __future__ import annotations

import json

from lulu_ads.widget import _escape_html, claude_apps_domain

TEMPLATES = ("stat-card", "table-card", "notice-card", "carousel-card")

_TEMPLATE_PLACEHOLDER = "__LW_TEMPLATE__"
_CONFIG_PLACEHOLDER = "__LW_CONFIG__"

# The single shared frame: tokens + primitives + per-template CSS + the
# strip (visuals verbatim from the approved gallery mock, including the
# rail gradient, strip gradient, and the ~7s sheen sweep -- which is
# disabled entirely under prefers-reduced-motion) + host bridge + the four
# template renderers. TEMPLATE/CONFIG are substituted at registration time;
# CONFIG rides an HTML attribute (read back via getAttribute, never
# innerHTML) so a hostile mapping string can't break out of the markup.
FRAME_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  /* Transparent canvas on both host themes -- the lulu-ads 0.7.4 fix. */
  html, body { background: transparent; color-scheme: light dark; margin: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  :root {
    --lw-radius: 16px;
    --lw-ink: #f5f2ee;
    --lw-ink-soft: rgba(255,255,255,.72);
    --lw-ink-faint: rgba(255,255,255,.5);
    --lw-orange: #E8763C;
    --lw-mono: "SF Mono", ui-monospace, Menlo, monospace;
  }
  .lw-card {
    position: relative;
    border-radius: var(--lw-radius);
    overflow: hidden;
    color: var(--lw-ink);
    background: linear-gradient(168deg, #2a2723 0%, #232019 100%);
    box-shadow: 0 1px 2px rgba(0,0,0,.25), 0 10px 26px -12px rgba(0,0,0,.5);
    isolation: isolate;
  }
  .lw-body { padding: 18px 20px 16px; }
  .lw-eyebrow {
    font-size: 11px; font-weight: 700; letter-spacing: .14em;
    text-transform: uppercase; color: var(--lw-ink-soft);
    text-shadow: 0 1px 2px rgba(0,0,0,.18);
  }
  .lw-value {
    font-size: 58px; font-weight: 300; line-height: 1.05; letter-spacing: -.02em;
    margin-top: 6px; text-shadow: 0 1px 3px rgba(0,0,0,.18);
  }
  .lw-sublabel { font-size: 13px; color: var(--lw-ink-soft); margin-top: 2px; }
  .lw-topright { position: absolute; top: 18px; right: 20px; text-align: right; }
  .lw-cond { font-size: 15px; font-weight: 600; text-shadow: 0 1px 2px rgba(0,0,0,.2); }
  .lw-chips { display: flex; gap: 6px; justify-content: flex-end; margin-top: 10px; flex-wrap: wrap; }
  .lw-chip {
    font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 999px;
    background: rgba(0,0,0,.22); backdrop-filter: blur(2px);
  }
  .lw-attr { font-size: 10px; color: var(--lw-ink-faint); margin-top: 6px; }
  .lw-glyph {
    width: 48px; height: 48px; border-radius: 50%; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 24px; color: #fff; font-weight: 700;
  }
  .lw-glyph[data-verdict="ok"]   { background: #2ecc71; }
  .lw-glyph[data-verdict="warn"] { background: #f0a532; }
  .lw-glyph[data-verdict="fail"] { background: #e05c4a; }
  .lw-row {
    display: flex; justify-content: space-between; gap: 12px;
    font-size: 13.5px; color: var(--lw-ink-soft); padding: 7px 0;
    border-top: 1px solid rgba(255,255,255,.08);
  }
  .lw-row b { color: var(--lw-ink); font-weight: 600; text-align: right; }

  /* stat-card atmospheres (condition-keyed; weather's WMO set, generalized) */
  .lw-card[data-atmo="clear"]   { background:
      radial-gradient(120% 90% at 82% -18%, rgba(255,241,180,.55) 0%, rgba(255,214,120,.18) 34%, transparent 60%),
      linear-gradient(168deg, #3d8fd8 0%, #4f9de0 45%, #7db8e8 100%); }
  .lw-card[data-atmo="partly"]  { background:
      radial-gradient(60% 55% at 78% 18%, rgba(255,255,255,.34) 0%, rgba(255,255,255,.10) 45%, transparent 70%),
      radial-gradient(50% 45% at 20% 68%, rgba(255,255,255,.16) 0%, transparent 65%),
      linear-gradient(168deg, #4a7fb5 0%, #5d90c2 50%, #86abd0 100%); }
  .lw-card[data-atmo="overcast"]{ background: linear-gradient(168deg, #5a6b7d 0%, #66788a 55%, #75879a 100%); }
  .lw-card[data-atmo="rain"]    { background:
      repeating-linear-gradient(112deg, rgba(255,255,255,.05) 0 2px, transparent 2px 14px),
      linear-gradient(168deg, #3e4c5e 0%, #49586b 50%, #566779 100%); }
  .lw-card[data-atmo="thunder"] { background:
      radial-gradient(70% 45% at 62% 8%, rgba(255,240,170,.20) 0%, transparent 55%),
      repeating-linear-gradient(112deg, rgba(255,255,255,.045) 0 2px, transparent 2px 16px),
      linear-gradient(168deg, #2b3442 0%, #353f4f 55%, #414d5f 100%); }
  .lw-card[data-atmo="snow"]    { background:
      radial-gradient(3px 3px at 22% 30%, rgba(255,255,255,.8) 40%, transparent 60%),
      radial-gradient(2.5px 2.5px at 61% 14%, rgba(255,255,255,.7) 40%, transparent 60%),
      radial-gradient(2px 2px at 83% 44%, rgba(255,255,255,.6) 40%, transparent 60%),
      radial-gradient(2.5px 2.5px at 42% 58%, rgba(255,255,255,.5) 40%, transparent 60%),
      linear-gradient(168deg, #7d93a8 0%, #90a5b8 55%, #a6b8c8 100%); }
  .lw-card[data-atmo="fog"]     { background:
      linear-gradient(180deg, rgba(255,255,255,.22) 0%, transparent 45%),
      linear-gradient(168deg, #8b98a5 0%, #9aa6b1 55%, #adb8c1 100%); }

  /* table-card */
  .lw-table { width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 12px; }
  .lw-table th {
    font-size: 11px; letter-spacing: .14em; text-transform: uppercase;
    color: var(--lw-ink-faint); text-align: left; padding: 4px 8px; font-weight: 600;
  }
  .lw-table th.num { text-align: right; }
  .lw-table td { padding: 10px 8px; border-top: 1px solid rgba(255,255,255,.07); }
  .lw-table td.num { font-family: var(--lw-mono); color: #7ee2a8; text-align: right; }
  .lw-table tr.best td { background: rgba(232,118,60,.12); }
  .lw-table tr.best td:first-child { border-left: 3px solid var(--lw-orange); }
  .lw-table tr.linked { cursor: pointer; }
  .lw-table tr.linked:hover td { background: rgba(255,255,255,.045); }
  .lw-best-badge {
    font-size: 10px; font-weight: 800; color: var(--lw-orange);
    letter-spacing: .06em; margin-left: 8px;
  }

  /* notice-card */
  .lw-notice { display: flex; gap: 16px; align-items: flex-start; }
  .lw-notice-title { font-size: 21px; font-weight: 700; margin-top: 4px; }
  .lw-card[data-verdict-bg="ok"]   { background: linear-gradient(150deg, #1f3327, #182a20); }
  .lw-card[data-verdict-bg="warn"] { background: linear-gradient(150deg, #38301c, #2b2517); }
  .lw-card[data-verdict-bg="fail"] { background: linear-gradient(150deg, #3a2320, #2b1a18); }

  /* carousel-card */
  .lw-track {
    display: flex; gap: 12px; overflow-x: auto; padding: 4px 2px;
    scroll-snap-type: x mandatory; margin-top: 12px; scrollbar-width: none;
  }
  .lw-track::-webkit-scrollbar { display: none; }
  .lw-opt {
    scroll-snap-align: start; min-width: 180px; max-width: 220px;
    background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.09);
    border-radius: 12px; padding: 14px; flex-shrink: 0;
  }
  .lw-opt .t { font-weight: 700; font-size: 14px; }
  .lw-opt .d { font-size: 12px; color: var(--lw-ink-soft); margin-top: 3px; }
  .lw-opt .p { font-family: var(--lw-mono); color: #7ee2a8; font-size: 16px; margin-top: 10px; }
  .lw-opt.sel { border-color: var(--lw-orange); background: rgba(232,118,60,.1); }
  .lw-dots { display: flex; gap: 5px; justify-content: center; margin-top: 10px; }
  .lw-dot { width: 6px; height: 6px; border-radius: 50%; background: rgba(255,255,255,.25); }
  .lw-dot.on { background: var(--lw-orange); }

  /* SPONSORED strip -- fixed by the SDK, verbatim from the approved mock
     (final): rounded gradient chip (no full-height rail), one-shot sheen,
     and a column reflow on narrow iframes. One DOM structure for both
     layouts -- on desktop the row wrappers are display:contents so the
     leaf elements flatten into the strip's own flex row (ordered), and
     the <=440px media query restores the wrappers into the stacked
     chip-bar + logo/text column layout. */
  .lw-strip {
    display: none; align-items: center; gap: 10px; padding: 9px 14px;
    background: rgba(0,0,0,.30);
    font-size: 12.5px; position: relative; overflow: hidden; cursor: pointer;
  }
  .lw-strip.show { display: flex; }
  .lw-strip::after {
    content: ""; position: absolute; top: 0; bottom: 0; width: 55%; left: -60%;
    background: linear-gradient(105deg, transparent 0%, rgba(255,255,255,.10) 45%,
      rgba(255,214,178,.14) 50%, rgba(255,255,255,.10) 55%, transparent 100%);
    animation: lw-shine 2.4s ease-out .8s 1 forwards; pointer-events: none;
  }
  @keyframes lw-shine { 0% { left: -60%; } 100% { left: 120%; } }
  @media (prefers-reduced-motion: reduce) { .lw-strip::after { animation: none; display: none; } }
  .lw-strip .toprow, .lw-strip .bottomrow, .lw-strip .rightcol, .lw-strip .ctarow { display: contents; }
  .lw-strip .badge {
    background: linear-gradient(180deg, #F5A053 0%, #E8763C 55%, #D95F27 100%);
    color: #fff; font-size: 9.5px; font-weight: 800; letter-spacing: .12em;
    border-radius: 6px; padding: 4px 9px; flex-shrink: 0; order: 0;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.25);
  }
  .lw-logo {
    width: 26px; height: 26px; border-radius: 7px; background: #fff;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; overflow: hidden; order: 1;
  }
  .lw-logo img { width: 18px; height: 18px; object-fit: contain; }
  .lw-logo.fallback { color: #fff; font-weight: 800; font-size: 13px; }
  .lw-strip .txt {
    flex: 1; color: var(--lw-ink); white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis; order: 2; min-width: 0;
  }
  .lw-strip .cta { color: #FFC46B; font-weight: 700; white-space: nowrap; flex-shrink: 0; order: 3; }
  .lw-strip .via { font-size: 11px; color: var(--lw-ink-faint); white-space: nowrap; flex-shrink: 0; order: 4; }
  @media (max-width: 440px) {
    .lw-strip.show { flex-direction: column; align-items: stretch; gap: 8px; padding: 0 0 10px; }
    .lw-strip .badge, .lw-logo, .lw-strip .txt, .lw-strip .cta, .lw-strip .via { order: 0; }
    .lw-strip .toprow {
      display: flex; align-items: center; justify-content: space-between;
      background: linear-gradient(180deg, #F5A053 0%, #E8763C 55%, #D95F27 100%);
      padding: 6px 14px; box-shadow: inset 0 1px 0 rgba(255,255,255,.25);
    }
    .lw-strip .toprow .badge { background: none; box-shadow: none; padding: 0; border-radius: 0; }
    .lw-strip .toprow .via { color: rgba(255,255,255,.85); }
    .lw-strip .bottomrow { display: flex; gap: 11px; align-items: flex-start; padding: 0 14px; }
    .lw-strip .rightcol { display: block; flex: 1; min-width: 0; }
    .lw-strip .txt {
      white-space: normal; overflow: visible; display: -webkit-box;
      -webkit-line-clamp: 3; -webkit-box-orient: vertical; line-height: 1.45;
    }
    .lw-strip .ctarow { display: flex; justify-content: space-between; align-items: center; margin-top: 6px; }
    .lw-value { font-size: 46px; }
  }

  .lw-skel { height: 84px; }
  .lw-err { padding: 22px 20px 26px; font-size: 14px; color: var(--lw-ink-soft); }
</style>
</head>
<body>
  <div class="lw-card" id="card" data-lw-config="__LW_CONFIG__">
    <div id="body-slot"><div class="lw-skel" id="skel"></div></div>
    <div class="lw-strip" id="strip">
      <div class="toprow">
        <span class="badge">SPONSORED</span>
        <span class="via">via Lulu Ads</span>
      </div>
      <div class="bottomrow">
        <span class="lw-logo" id="sp-logo" style="display:none"></span>
        <div class="rightcol">
          <span class="txt" id="sp-text"></span>
          <div class="ctarow"><span class="cta" id="sp-cta">Learn more →</span></div>
        </div>
      </div>
    </div>
  </div>

<script>
(function () {
  "use strict";
  var TEMPLATE = "__LW_TEMPLATE__";
  var CONFIG = {};
  try { CONFIG = JSON.parse(document.getElementById("card").getAttribute("data-lw-config")) || {}; } catch (e) {}
  var MAPPING = CONFIG.mapping || {};

  function post(msg) { try { window.parent.postMessage(msg, "*"); } catch (e) {} }
  var nextId = 1, pending = {};
  function request(method, params, cb) {
    var id = nextId++;
    pending[id] = cb || function () {};
    post({ jsonrpc: "2.0", id: id, method: method, params: params });
  }
  function sizeChanged() {
    var h = document.body.scrollHeight;
    if (h) post({ jsonrpc: "2.0", method: "ui/notifications/size-changed", params: { width: 400, height: h } });
  }
  /* Dual-protocol handshake. MCP Apps (stable 2026-01-26) hosts require a
     ui/initialize REQUEST and only deliver tool-result after it completes;
     draft-era hosts ignore the unknown request entirely. So: send the
     request; if it's answered we're on the new runtime (apply hostContext,
     then notify initialized per spec order); if not, a grace timeout falls
     back to the legacy fire-and-forget initialized. Both paths converge on
     the same tool-result listener, guarded by `rendered`. */
  var sentInit = false, newProto = false;
  function sendInitialized() {
    if (sentInit) return;
    sentInit = true;
    post({ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} });
    sizeChanged();
  }
  request("ui/initialize", {
    appInfo: { name: "lulu-ads-result", version: "1.0.0" },
    appCapabilities: {},
    protocolVersion: "2026-01-26"
  }, function (err, result) {
    newProto = true;
    if (result && result.hostContext && result.hostContext.theme) {
      document.documentElement.setAttribute("data-theme", result.hostContext.theme);
    }
    sendInitialized();
  });
  function legacyInit() { setTimeout(sendInitialized, 400); }
  if (document.readyState === "complete") legacyInit();
  else window.addEventListener("load", legacyInit);
  setTimeout(sendInitialized, 900);

  /* Third bridge: ChatGPT (OpenAI Apps). No postMessage handshake there —
     the host injects window.openai and hands the tool's structuredContent
     over as toolOutput (immediately or via an openai:set_globals event).
     Same render path, same idempotency guard. */
  function tryOpenAI() {
    var oa = window.openai;
    if (!oa) return;
    var out = oa.toolOutput;
    if (out && !window.__lwRendered) { renderOnce(out); }
  }
  window.addEventListener("openai:set_globals", function (ev) {
    var g = ev && ev.detail && ev.detail.globals;
    var out = (g && g.toolOutput) || (window.openai && window.openai.toolOutput);
    if (out) renderOnce(out);
  });
  tryOpenAI();
  setTimeout(tryOpenAI, 300);
  window.addEventListener("load", tryOpenAI);

  /* Host-agnostic link opening: ChatGPT wants openExternal, MCP Apps
     wants a ui/open-link request, draft hosts took the same shape as a
     notification — the request form covers both MCP generations. */
  function openLink(url) {
    if (window.openai && typeof window.openai.openExternal === "function") {
      try { window.openai.openExternal({ href: url }); return; } catch (e) {}
    }
    post({ jsonrpc: "2.0", id: "open-link-" + Date.now(), method: "ui/open-link", params: { url: url } });
  }

  /* mapping helpers ------------------------------------------------- */
  function getPath(obj, path) {
    if (obj == null || !path) return undefined;
    var parts = String(path).split(".");
    var cur = obj;
    for (var i = 0; i < parts.length; i++) {
      if (cur == null) return undefined;
      cur = cur[parts[i]];
    }
    return cur;
  }
  function fmt(v) {
    if (v === null || v === undefined) return "";
    if (typeof v === "number" && isFinite(v)) {
      if (v === 0) return "0";
      var abs = Math.abs(v);
      var d = abs >= 100 ? 0 : abs >= 1 ? 2 : abs >= 0.01 ? 4 : 6;
      var s = v.toFixed(d);
      if (d > 0) s = s.replace(/0+$/, "").replace(/\.$/, "");
      return s;
    }
    if (Array.isArray(v)) return v.map(fmt).join(" · ");
    return String(v);
  }
  // entry = "dot.path" | {path, prefix, suffix}; scope = object to read from
  function resolve(entry, scope) {
    if (entry === null || entry === undefined) return "";
    if (typeof entry === "string") return fmt(getPath(scope, entry));
    var raw = getPath(scope, entry.path);
    if (raw === null || raw === undefined || raw === "") return "";
    return (entry.prefix || "") + fmt(raw) + (entry.suffix || "");
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== "") e.textContent = text;
    return e;
  }

  /* condition -> atmosphere bucket (WMO codes or descriptive words) -- */
  function bucketOf(v) {
    var code = (typeof v === "number") ? v : NaN;
    if (isFinite(code)) {
      if (code === 0 || code === 1) return "clear";
      if (code === 2) return "partly";
      if (code === 3) return "overcast";
      if (code === 45 || code === 48) return "fog";
      if (code >= 95) return "thunder";
      if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "snow";
      if (code >= 51) return "rain";
      return "overcast";
    }
    var desc = String(v || "").toLowerCase();
    if (!desc) return "";
    if (/thunder/.test(desc)) return "thunder";
    if (/snow/.test(desc)) return "snow";
    if (/fog|rime|mist/.test(desc)) return "fog";
    if (/rain|drizzle|shower/.test(desc)) return "rain";
    if (/overcast/.test(desc)) return "overcast";
    if (/partly|mainly/.test(desc)) return "partly";
    if (/clear|sun/.test(desc)) return "clear";
    return "";
  }

  /* template renderers ----------------------------------------------- */
  function renderStat(sc, slot) {
    var body = el("div", "lw-body");
    var left = el("div");
    left.appendChild(el("div", "lw-eyebrow", resolve(MAPPING.eyebrow, sc) || " "));
    left.appendChild(el("div", "lw-value", resolve(MAPPING.value, sc)));
    var sub = resolve(MAPPING.sublabel, sc);
    if (sub) left.appendChild(el("div", "lw-sublabel", sub));
    body.appendChild(left);
    var right = el("div", "lw-topright");
    var cond = resolve(MAPPING.condition, sc);
    if (cond) right.appendChild(el("div", "lw-cond", cond.charAt(0).toUpperCase() + cond.slice(1)));
    var chips = el("div", "lw-chips");
    (MAPPING.chips || []).forEach(function (c) {
      var t = resolve(c, sc);
      if (t) chips.appendChild(el("span", "lw-chip", t));
    });
    if (chips.children.length) right.appendChild(chips);
    var attr = resolve(MAPPING.attribution, sc) || (MAPPING.attribution_text || "");
    if (attr) right.appendChild(el("div", "lw-attr", attr));
    body.appendChild(right);
    slot.appendChild(body);
    if (MAPPING.atmosphere) {
      var b = bucketOf(getPath(sc, typeof MAPPING.atmosphere === "string" ? MAPPING.atmosphere : MAPPING.atmosphere.path));
      if (b) document.getElementById("card").setAttribute("data-atmo", b);
    }
  }

  function renderTable(sc, slot) {
    var body = el("div", "lw-body");
    var eyebrow = resolve(MAPPING.eyebrow, sc);
    if (eyebrow) body.appendChild(el("div", "lw-eyebrow", eyebrow));
    var rows = getPath(sc, MAPPING.rows);
    if (!Array.isArray(rows)) rows = [];
    var table = el("table", "lw-table");
    var thead = el("tr");
    (MAPPING.columns || []).forEach(function (col) {
      var th = el("th", col.align === "right" || col.mono ? "num" : "", col.header || "");
      thead.appendChild(th);
    });
    table.appendChild(thead);
    rows.forEach(function (row) {
      var best = MAPPING.highlight ? !!getPath(row, MAPPING.highlight) : false;
      var classes = best ? "best" : "";
      // rowLink: a dot-path (or {path} entry) resolving to a per-row URL --
      // e.g. a publisher's own booking/checkout link. Opened via the same
      // host-agnostic openLink() the sponsored strip already uses. Absent
      // by default; a row with no resolvable URL renders exactly as before
      // (no cursor change, no click handler).
      var rowUrl = MAPPING.rowLink
        ? getPath(row, typeof MAPPING.rowLink === "string" ? MAPPING.rowLink : MAPPING.rowLink.path)
        : undefined;
      if (rowUrl) classes = (classes + " linked").trim();
      var tr = el("tr", classes);
      (MAPPING.columns || []).forEach(function (col, ci) {
        var td = el("td", col.mono || col.align === "right" ? "num" : "", resolve(col, row));
        if (ci === 0 && best) td.appendChild(el("span", "lw-best-badge", "BEST"));
        tr.appendChild(td);
      });
      if (rowUrl) tr.addEventListener("click", function () { openLink(String(rowUrl)); });
      table.appendChild(tr);
    });
    body.appendChild(table);
    slot.appendChild(body);
  }

  function renderNotice(sc, slot) {
    var body = el("div", "lw-body");
    var wrap = el("div", "lw-notice");
    var verdict = "ok";
    if (typeof MAPPING.verdict === "string" || (MAPPING.verdict && MAPPING.verdict.path)) {
      var raw = getPath(sc, typeof MAPPING.verdict === "string" ? MAPPING.verdict : MAPPING.verdict.path);
      verdict = raw ? "ok" : "fail";
    }
    if (MAPPING.verdict_override === "warn") verdict = "warn";
    var g = el("div", "lw-glyph", verdict === "ok" ? "✓" : verdict === "warn" ? "!" : "✕");
    g.setAttribute("data-verdict", verdict);
    wrap.appendChild(g);
    var col = el("div"); col.style.flex = "1";
    var eyebrow = resolve(MAPPING.eyebrow, sc);
    if (eyebrow) col.appendChild(el("div", "lw-eyebrow", eyebrow));
    col.appendChild(el("div", "lw-notice-title", resolve(MAPPING.title, sc)));
    var rowsWrap = el("div"); rowsWrap.style.marginTop = "10px";
    (MAPPING.rows || []).forEach(function (pair) {
      var label = pair[0], entry = pair[1];
      var val = resolve(entry, sc);
      if (!val) return;
      var r = el("div", "lw-row");
      r.appendChild(el("span", "", label));
      r.appendChild(el("b", "", val));
      rowsWrap.appendChild(r);
    });
    col.appendChild(rowsWrap);
    wrap.appendChild(col);
    body.appendChild(wrap);
    slot.appendChild(body);
    document.getElementById("card").setAttribute("data-verdict-bg", verdict);
  }

  function renderCarousel(sc, slot) {
    var body = el("div", "lw-body");
    var eyebrow = resolve(MAPPING.eyebrow, sc);
    if (eyebrow) body.appendChild(el("div", "lw-eyebrow", eyebrow));
    var items = getPath(sc, MAPPING.items);
    if (!Array.isArray(items)) items = [];
    var track = el("div", "lw-track");
    var dots = el("div", "lw-dots");
    var im = MAPPING.item || {};
    items.forEach(function (item, i) {
      var sel = MAPPING.highlight ? !!getPath(item, MAPPING.highlight) : false;
      var opt = el("div", "lw-opt" + (sel ? " sel" : ""));
      opt.appendChild(el("div", "t", resolve(im.title, item)));
      var d = resolve(im.detail, item);
      if (d) opt.appendChild(el("div", "d", d));
      var p = resolve(im.price, item);
      if (p) opt.appendChild(el("div", "p", p));
      track.appendChild(opt);
      dots.appendChild(el("span", "lw-dot" + (i === 0 ? " on" : "")));
    });
    body.appendChild(track);
    if (items.length > 1) body.appendChild(dots);
    slot.appendChild(body);
    track.addEventListener("scroll", function () {
      var idx = Math.round(track.scrollLeft / Math.max(1, track.scrollWidth - track.clientWidth) * (items.length - 1));
      for (var i = 0; i < dots.children.length; i++) dots.children[i].className = "lw-dot" + (i === idx ? " on" : "");
    });
  }

  /* SPONSORED strip -- fixed contract, body code never touches this. -- */
  var FALLBACK_BGS = ["#7c5cff", "#2f9e8f", "#c2544f", "#3f74c9", "#b0812c", "#8352a8"];
  function hashCode(s) {
    var h = 0;
    for (var i = 0; i < s.length; i++) { h = ((h << 5) - h + s.charCodeAt(i)) | 0; }
    return Math.abs(h);
  }
  function renderSponsored(sc) {
    var s = sc && sc.sponsored;
    if (!s || typeof s.text !== "string" || typeof s.url !== "string" || !s.text || !s.url) return;
    document.getElementById("sp-text").textContent = s.text;
    var brandWord = (s.text.match(/[A-Za-z0-9][\w.\-]*/) || [""])[0];
    var logo = document.getElementById("sp-logo");
    function letterTile() {
      logo.textContent = (brandWord.charAt(0) || "•").toUpperCase();
      logo.className = "lw-logo fallback";
      logo.style.background = FALLBACK_BGS[hashCode(brandWord || s.text) % FALLBACK_BGS.length];
      logo.style.display = "flex";
    }
    /* Field names arrive snake_case from the Python SDK and camelCase from
       the JS SDK's Sponsored type -- accept both. */
    var logoUrl = (typeof s.logo_url === "string" && s.logo_url) ? s.logo_url
      : (typeof s.logoUrl === "string" ? s.logoUrl : "");
    if (logoUrl) {
      var img = document.createElement("img");
      img.alt = "";
      img.onload = function () { logo.textContent = ""; logo.className = "lw-logo"; logo.style.background = "#fff"; logo.appendChild(img); logo.style.display = "flex"; };
      img.onerror = letterTile;
      img.src = logoUrl;
    } else {
      letterTile();
    }
    var strip = document.getElementById("strip");
    strip.classList.add("show");
    /* Rendered-impression beacon: fires exactly when the strip becomes
       visible -- never on mere API output -- so CPM counts what a human
       actually saw. Fire-and-forget; a blocked/failed pixel changes
       nothing visually. */
    var impUrl = (typeof s.imp_url === "string" && s.imp_url) ? s.imp_url
      : (typeof s.impUrl === "string" ? s.impUrl : "");
    if (impUrl && !strip.dataset.impFired) {
      strip.dataset.impFired = "1";
      var px = new Image(1, 1);
      px.src = impUrl;
    }
    strip.addEventListener("click", function () { openLink(s.url); });
  }

  var RENDERERS = {
    "stat-card": renderStat,
    "table-card": renderTable,
    "notice-card": renderNotice,
    "carousel-card": renderCarousel
  };

  function render(sc) {
    if (!sc || typeof sc !== "object") return;
    var slot = document.getElementById("body-slot");
    slot.innerHTML = "";
    if (sc.error) {
      slot.appendChild(el("div", "lw-err", String(sc.error)));
    } else if (CONFIG.bodyHtml) {
      // Custom escape hatch: static, integrator-authored primitives-only
      // markup -- trusted by the same contract as the tool's own code.
      var wrap = el("div", "lw-body");
      wrap.innerHTML = CONFIG.bodyHtml;
      slot.appendChild(wrap);
    } else {
      (RENDERERS[TEMPLATE] || renderStat)(sc, slot);
    }
    renderSponsored(sc);
    sizeChanged();
  }

  function renderOnce(sc) {
    if (window.__lwRendered || !sc) return;
    window.__lwRendered = true;
    try { render(sc); } catch (e) { /* leave skeleton */ }
    sizeChanged();
  }

  window.addEventListener("message", function (ev) {
    /* Gate on source, never origin (spec: sandbox proxies vary origins). */
    if (ev.source && ev.source !== window.parent) return;
    var data = ev && ev.data;
    if (!data) return;
    if (data.id != null && data.method == null) {
      /* Response to one of our requests (ui/initialize, ui/open-link). */
      var cb = pending[data.id];
      delete pending[data.id];
      if (cb) cb(data.error || null, data.result);
      return;
    }
    if (data.method === "ui/resource-teardown" && data.id != null) {
      /* Spec requires an answer or the host logs the view as hung. */
      post({ jsonrpc: "2.0", id: data.id, result: {} });
      return;
    }
    if (data.method !== "ui/notifications/tool-result") return;
    renderOnce((data.params || {}).structuredContent);
  });
})();
</script>
</body>
</html>
"""


def result_widget_html(
    *,
    template: str,
    mapping: dict | None = None,
    body_html: str | None = None,
) -> str:
    """Builds the self-contained widget HTML for one tool: the shared frame
    with this tool's template + mapping substituted in. Exposed separately
    from registration for tests and snapshotting.
    """
    if template not in TEMPLATES:
        raise ValueError(
            f"unknown template {template!r} -- expected one of {', '.join(TEMPLATES)}"
        )
    config: dict = {"mapping": mapping or {}}
    if body_html:
        config["bodyHtml"] = body_html
    config_json = json.dumps(config, separators=(",", ":"), ensure_ascii=False)
    return (
        FRAME_HTML
        .replace(_CONFIG_PLACEHOLDER, _escape_html(config_json))
        .replace(_TEMPLATE_PLACEHOLDER, template)
    )


def register_result_widget(
    mcp,
    tool: str,
    *,
    template: str = "stat-card",
    mapping: dict | None = None,
    endpoint_url: str,
    body_html: str | None = None,
    resource_uri: str | None = None,
    visibility: list | None = None,
):
    """Registers a predefined result widget for ``tool`` and attaches it.

    Call AFTER the tool is registered (module import order: define your
    ``@mcp.tool`` functions, then call this) -- the tool's MCP Apps config
    is patched in place, deliberately overriding ``enable_lulu_ads``'s
    generic sponsored-card widget for this tool. The sponsored DATA field
    still flows from the middleware and renders inside this widget as the
    fixed disclosed strip.

    Also returns the AppConfig, so passing ``app=`` explicitly at
    registration time keeps working for integrators who prefer that order::

        cfg = register_result_widget(mcp, "search", template="table-card", ...)
        @mcp.tool(app=cfg)          # only needed if "search" wasn't
        def search(...): ...        # registered before the call

    Requires fastmcp (not a hard dependency of this package -- only of
    this module, same pattern as middleware.py / widget.py).
    """
    from fastmcp.apps.config import AppConfig

    uri = resource_uri or f"ui://lulu-ads/result-{tool}.html"
    domain = claude_apps_domain(endpoint_url)
    html = result_widget_html(template=template, mapping=mapping, body_html=body_html)

    # MCP Apps hosts apply a default CSP of img-src 'self' data: — the
    # rendered-impression beacon (a 1px <img> to ads.getlulu.dev) is
    # blocked unless the resource declares the domain. connect_domains
    # rides along for a future sendBeacon variant. Older fastmcp versions
    # without ResourceCSP just skip the declaration (beacon falls back to
    # blocked-on-web, which the served-count upper bound already covers).
    resource_app = AppConfig(domain=domain)
    try:
        from fastmcp.apps.config import ResourceCSP

        resource_app = AppConfig(
            domain=domain,
            csp=ResourceCSP(
                resource_domains=["https://ads.getlulu.dev"],
                connect_domains=["https://ads.getlulu.dev"],
            ),
        )
    except (ImportError, TypeError):
        pass

    @mcp.resource(
        uri,
        name=f"result_widget_{tool}",
        mime_type="text/html;profile=mcp-app",
        app=resource_app,
    )
    def _result_widget_resource() -> str:
        return html

    app_config = AppConfig(resource_uri=uri, visibility=visibility or ["model"])

    # Patch the already-registered tool AND resource in place. `meta` is
    # where FastMCP folds `app=` at registration; mutating the live objects
    # persists because get_tool/get_resource return the same instances.
    # (The @mcp.resource meta= kwarg is silently dropped by some deployed
    # fastmcp versions — observed live 2026-07-30 — so the in-place patch
    # is the only reliable path for the ChatGPT keys.)
    #
    # ChatGPT (OpenAI Apps) discovers templates via the TOOL's
    # "openai/outputTemplate" and reads beacon/CSP permission from the
    # RESOURCE's "openai/widgetCSP" (snake_case) — declaring both alongside
    # the MCP Apps keys is what makes one widget host-agnostic.
    import asyncio

    _openai_csp = {
        "connect_domains": ["https://ads.getlulu.dev"],
        "resource_domains": ["https://ads.getlulu.dev"],
    }
    ui_meta = {
        "ui": {"resourceUri": uri, "visibility": visibility or ["model"]},
        "openai/outputTemplate": uri,
    }
    try:
        try:
            asyncio.get_running_loop()
            running = True
        except RuntimeError:
            running = False
        if not running:
            t = asyncio.run(mcp.get_tool(tool))
            t.meta = {**(t.meta or {}), **ui_meta}
            try:
                r = asyncio.run(mcp.get_resource(uri))
                r.meta = {**(r.meta or {}), "openai/widgetCSP": _openai_csp}
            except Exception:
                pass
    except Exception:
        # Tool not registered yet (or a running loop at import time):
        # the returned AppConfig via app= is the fallback path.
        pass

    return app_config
