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
  ``structuredContent.sponsored`` exists -- a cover card: a colorful cover
  band (a real image when the payload supplies ``cover_image_url``, an
  animated gradient otherwise) with "SPONSORED" pinned on it, a logo tile
  overlapping the seam into the body, then ad text -> CTA -> "via Lulu
  Ads". ``sponsored.logo_url`` renders in the tile with an automatic
  letter-tile fallback (brand initial, hash-derived background) on
  absence or load error, so a blocked or dead logo never leaves a hole;
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

# The SPONSORED strip's own visual template (LUL-69) -- independent of
# `template` above, which picks the result-widget's body layout (NOTE:
# `template="carousel-card"` is a body layout; this "carousel" is a
# different, unrelated thing -- the footer's own presentation). "card" is
# the default: a cover card (colorful cover band + overlapping logo tile +
# text + CTA), always fully visible. The others port widget.py's React
# templates into this frame's own vanilla-JS renderer (see
# renderSponsored()): "flip-card" (a teaser with the same cover identity,
# flips to reveal the offer on tap), "carousel" (auto-cycles between three
# framings of the SAME single sponsored payload -- a bigger brand logo, the
# offer text, then the CTA -- never multiple different sponsors: this
# frame only ever gets one sponsored payload per call, so unlike widget.py's
# carousel template
# there is no multi-advertiser rotation here, see LUL-49 for that separate,
# still-blocked, backend question), "scratch-reveal" (canvas foil layer
# over the offer text/CTA -- never over the cover band, so "SPONSORED"
# stays visible regardless of scratch state -- auto-reveals after 5s
# regardless of interaction, per LUL-52's guardrail: this is a reveal
# ANIMATION with one guaranteed, deterministic outcome, styled after a
# lottery scratch ticket but never actually gated or variable -- there is
# no "losing" state, which is exactly what keeps it out of gambling-
# mechanic territory despite the visual reference). "banner" is still a
# no-op here (redundant with "card"); the "single row, no room for a
# full-bleed image" reasoning that used to also exclude "hero" no longer
# holds now that the strip itself is cover-height -- worth a follow-up
# ticket, not resolved by this comment. "spin" shipped and was removed in
# the same release cycle -- a coin-flip scaleX on a small, often-flat
# letter-tile logo tile turned out to be visually illegible in practice
# (mid-animation it shrinks to a near-invisible sliver against a busy
# cover background), not just a subtle effect; replaced with "carousel"
# rather than patched, since sliding + dots is an unambiguous, widely
# recognized pattern where "what is this animation" was the exact failure
# mode. Only formats actually ported into this frame's own
# renderSponsored() get added here, not the whole standalone gallery
# automatically.
SPONSOR_TEMPLATES = ("card", "flip-card", "carousel", "scratch-reveal")

_TEMPLATE_PLACEHOLDER = "__LW_TEMPLATE__"
_SPONSOR_TEMPLATE_PLACEHOLDER = "__LW_SPONSOR_TEMPLATE__"
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

  /* SPONSORED strip -- a mini "cover card": a colorful cover band (a real
     sponsor image when the live payload supplies one via
     `cover_image_url`/`coverImageUrl`, an animated gradient otherwise)
     with the logo tile overlapping the seam between cover and body.
     "SPONSORED" is pinned on the cover band itself, never inside the
     body -- disclosure stays visible at impression time regardless of
     scratch/flip state (scratch's canvas only ever covers .lw-cover-body,
     flip-card's front face renders the same cover band). One shared set
     of `.lw-cover-*` primitives: default "card"/carousel/scratch-reveal
     render it directly into #strip; flip-card wraps two copies (front
     teaser, back = the real offer). */
  .lw-strip { display: none; position: relative; cursor: pointer; }
  .lw-strip.show { display: flex; }
  .lw-strip.lw-cover-card { flex-direction: column; overflow: visible; }
  /* flip-card's two faces are position:absolute; inset:0 (for the
     crossfade), which means each face's OWN offsetHeight just reflects
     that fixed box, never its content's natural height -- so the actual
     cover-card layout lives one level deeper, in a normal-flow
     `.lw-cover-card-inner` child. Measuring THAT child's offsetHeight
     (see renderSponsored's flip-card branch) gets the real content
     height regardless of the outer face's forced sizing. */
  .lw-strip-front {
    position: absolute; inset: 0; overflow: visible;
    opacity: 1; transition: opacity .3s;
  }
  @media (prefers-reduced-motion: reduce) { .lw-strip-front { transition: none; } }
  /* width:100% matters specifically for #strip-back: its OWN parent
     (.lw-strip-flip .lw-strip) is `display:flex` on the default row
     axis, so without an explicit width this flex item shrinks to its
     content's fit-content width on that axis instead of filling the
     card -- the front face doesn't have this problem (.lw-strip-front
     isn't a flex container), which is why the bug only ever showed up
     after the first flip. */
  .lw-cover-card-inner { display: flex; flex-direction: column; overflow: visible; position: relative; width: 100%; }

  .lw-cover {
    position: relative; height: 66px; overflow: hidden;
    background: linear-gradient(120deg, #ff8a3d 0%, #d94fd0 48%, #3ec6ff 100%);
    background-size: 220% 220%;
    animation: lw-cover-drift 10s ease-in-out infinite alternate;
  }
  .lw-cover.has-image { background-size: cover; background-position: center; animation: none; }
  @keyframes lw-cover-drift { 0% { background-position: 0% 20%; } 100% { background-position: 100% 80%; } }
  @media (prefers-reduced-motion: reduce) { .lw-cover { animation: none; } }
  .lw-cover-badge { position: absolute; top: 10px; left: 14px; }
  .lw-cover-logo {
    position: absolute; top: 40px; left: 14px; width: 52px; height: 52px;
    border-radius: 13px; border: 3px solid #241d16; z-index: 1;
  }
  .lw-cover-logo img { width: 34px; height: 34px; }
  .lw-cover-logo.fallback { font-size: 22px; }

  .lw-cover-body { position: relative; padding: 30px 16px 16px; overflow: hidden; background: rgba(0,0,0,.30); }
  .lw-cover-body::after {
    content: ""; position: absolute; top: 0; bottom: 0; width: 55%; left: -60%;
    background: linear-gradient(105deg, transparent 0%, rgba(255,255,255,.10) 45%,
      rgba(255,214,178,.14) 50%, rgba(255,255,255,.10) 55%, transparent 100%);
    animation: lw-shine 2.4s ease-out .8s 1 forwards; pointer-events: none;
  }
  @keyframes lw-shine { 0% { left: -60%; } 100% { left: 120%; } }
  @media (prefers-reduced-motion: reduce) { .lw-cover-body::after { animation: none; display: none; } }
  .lw-cover-info { display: flex; flex-direction: column; gap: 3px; }
  .lw-strip .txt, .lw-strip-front .txt { color: var(--lw-ink); font-weight: 600; }
  .lw-strip .via, .lw-strip-front .via { font-size: 11.5px; color: var(--lw-ink-faint); }
  .lw-cover-ctarow { margin-top: 12px; }
  .lw-strip .cta, .lw-strip-front .cta {
    display: inline-flex; align-items: center;
    color: #2a1d0f; font-weight: 800; white-space: nowrap;
    background: #FFC46B; padding: 8px 14px; border-radius: 999px; font-size: 12.5px;
    box-shadow: 0 2px 8px rgba(0,0,0,.2);
  }
  .lw-strip .badge, .lw-strip-front .badge {
    background: linear-gradient(180deg, #F5A053 0%, #E8763C 55%, #D95F27 100%);
    color: #fff; font-size: 10.5px; font-weight: 800; letter-spacing: .12em;
    border-radius: 6px; padding: 5px 10px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.25);
  }
  .lw-logo {
    width: 40px; height: 40px; border-radius: 10px; background: #fff;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; overflow: hidden; box-shadow: 0 2px 6px rgba(0,0,0,.25);
  }
  .lw-logo img { width: 28px; height: 28px; object-fit: contain; }
  .lw-logo.fallback { color: #fff; font-weight: 800; font-size: 18px; }

  /* SPONSORED strip: flip-card sponsor_template (LUL-69). Front face is
     the SAME cover-card primitives as the back (real logo, cover band,
     "SPONSORED" disclosure), just simpler copy -- "See today's offer" /
     "Tap to reveal" with a nudging arrow -- so tapping crossfades into
     the real offer without the visual identity changing underneath it.
     A crossfade rather than a true 3D rotation, which proved unreliable
     nested this deeply inside an already-sandboxed MCP Apps iframe. */
  .lw-strip-flip { display: none; position: relative; cursor: pointer; min-height: 146px; }
  .lw-strip-flip.show { display: block; }
  .lw-strip-flip.flipped .lw-strip-front { opacity: 0; pointer-events: none; }
  /* Overrides the base .lw-strip's own `display: none` -- visibility of
     the back face is controlled entirely by the OUTER .lw-strip-flip's
     flipped state above, not by adding .show to this nested element too
     (nothing ever does). Starts transparent (stacked under the front
     teaser) and crossfades in on .flipped, mirroring the front's own
     fade so nothing pops instantly in either direction. */
  .lw-strip-flip .lw-strip {
    display: flex; position: absolute; inset: 0; opacity: 0; transition: opacity .3s;
  }
  .lw-strip-flip.flipped .lw-strip { opacity: 1; }
  @media (prefers-reduced-motion: reduce) { .lw-strip-flip .lw-strip { transition: none; } }
  .lw-flip-arrow { display: inline-block; margin-left: 3px; animation: lw-flip-nudge 1.6s ease-in-out .8s infinite; }
  @keyframes lw-flip-nudge { 0%, 100% { transform: translateX(0); } 50% { transform: translateX(4px); } }
  @media (prefers-reduced-motion: reduce) { .lw-flip-arrow { animation: none; } }

  /* SPONSORED strip: carousel sponsor_template (LUL-69, replacing the
     removed "spin" -- see SPONSOR_TEMPLATES's own comment for why). All
     three slides are the SAME single sponsored payload, just different
     framings of it (big logo, offer text, CTA) -- never multiple
     sponsors. Content is visible immediately regardless of which slide is
     showing; the click-to-navigate handler on #strip works identically
     for all three. A few auto-advance cycles, then settles on the CTA
     slide, echoing spin's own "plays a bit, then rests" ethos -- never an
     endless loop nagging inside someone else's UI. */
  .lw-carousel-viewport { overflow: hidden; }
  .lw-carousel-track { display: flex; transition: transform .5s cubic-bezier(.4,0,.2,1); }
  .lw-carousel-slide {
    flex: 0 0 100%; min-width: 0; display: flex; flex-direction: column; justify-content: center;
  }
  .lw-carousel-slide.lw-slide-cta { align-items: flex-start; }
  /* Slide 1 is a visual brand moment, not invented copy -- earlier this
     tried a "headline" made from the same word the logo's letter-tile
     fallback uses, but that word is just whatever `sponsored.text`
     happens to start with ("Book direct and..." -> "Book"), which reads
     as a non-sequitur on its own with no sentence around it. A bigger
     rendering of the SAME real logo has no such failure mode. */
  .lw-carousel-slide.lw-slide-brand { flex-direction: row; align-items: center; gap: 12px; }
  .lw-carousel-logo-big { width: 56px; height: 56px; border-radius: 14px; }
  .lw-carousel-logo-big img { width: 38px; height: 38px; }
  .lw-carousel-logo-big.fallback { font-size: 24px; }
  @media (prefers-reduced-motion: reduce) { .lw-carousel-track { transition: none; } }
  .lw-carousel-dots { display: flex; gap: 6px; margin-top: 12px; }
  .lw-carousel-dots .lw-dot {
    width: 6px; height: 6px; border-radius: 50%; background: rgba(255,255,255,.28);
    transition: background .3s;
  }
  .lw-carousel-dots .lw-dot.on { background: #FFC46B; }

  /* SPONSORED strip: scratch-reveal sponsor_template (LUL-69/52) --
     styled as a real foil lottery-ticket stub (metallic sheen, diagonal
     hatch, a perforation line, a ticket glyph), but functionally a
     GUARANTEED reveal, never a chance mechanic: there is exactly one
     outcome and no "losing" state, which is what keeps the ticket
     styling from crossing into an actual gambling mechanic. The canvas
     fills ONLY .lw-cover-body (offer text + CTA) -- never .lw-cover,
     which holds the logo and the "SPONSORED" disclosure, so disclosure
     stays visible at impression time no matter how much (or little) is
     scratched. .lw-cover-body already has `position: relative; overflow:
     hidden` (see its rule above), so this only needs to fill that
     existing box. Auto-reveals after 5s regardless of interaction --
     long enough to actually feel like scratching something (3s proved
     too short to register as an interaction at all) -- but still
     unconditional (binding guardrail: the offer underneath never depends
     on whether or how much the user scratched -- see the JS timer in
     setupScratchReveal). */
  .lw-scratch-canvas { position: absolute; inset: 0; cursor: pointer; touch-action: none; }

  .lw-skel { height: 84px; }
  .lw-err { padding: 22px 20px 26px; font-size: 14px; color: var(--lw-ink-soft); }
</style>
</head>
<body>
  <div class="lw-card" id="card" data-lw-config="__LW_CONFIG__">
    <div id="body-slot"><div class="lw-skel" id="skel"></div></div>
    <div class="lw-strip lw-cover-card" id="strip">
      <div class="lw-cover" id="sp-cover">
        <span class="badge lw-cover-badge">SPONSORED</span>
      </div>
      <span class="lw-logo lw-cover-logo" id="sp-logo" style="display:none"></span>
      <div class="lw-cover-body" id="sp-body">
        <div class="lw-cover-info">
          <span class="txt" id="sp-text"></span>
          <span class="via">via Lulu Ads</span>
        </div>
        <div class="lw-cover-ctarow"><span class="cta" id="sp-cta">Learn more →</span></div>
        <canvas class="lw-scratch-canvas" id="scratch-canvas" style="display:none"></canvas>
      </div>
    </div>
    <div class="lw-strip lw-cover-card" id="strip-carousel">
      <div class="lw-cover" id="sp-cover-carousel">
        <span class="badge lw-cover-badge">SPONSORED</span>
      </div>
      <span class="lw-logo lw-cover-logo" id="sp-logo-carousel" style="display:none"></span>
      <div class="lw-cover-body">
        <div class="lw-carousel-viewport">
          <div class="lw-carousel-track" id="carousel-track">
            <div class="lw-carousel-slide lw-slide-brand">
              <span class="lw-logo lw-carousel-logo-big" id="sp-logo-carousel-big" style="display:none"></span>
              <span class="via">via Lulu Ads</span>
            </div>
            <div class="lw-carousel-slide">
              <div class="lw-cover-info">
                <span class="txt" id="sp-text-carousel"></span>
                <span class="via">via Lulu Ads</span>
              </div>
            </div>
            <div class="lw-carousel-slide lw-slide-cta">
              <span class="cta" id="sp-cta-carousel">Learn more →</span>
            </div>
          </div>
        </div>
        <div class="lw-carousel-dots" id="carousel-dots">
          <span class="lw-dot on"></span><span class="lw-dot"></span><span class="lw-dot"></span>
        </div>
      </div>
    </div>
    <div class="lw-strip-flip" id="strip-flip">
      <div class="lw-strip-front">
        <div class="lw-cover-card-inner" id="front-inner">
          <div class="lw-cover" id="sp-cover-flip-front">
            <span class="badge lw-cover-badge">SPONSORED</span>
          </div>
          <span class="lw-logo lw-cover-logo" id="sp-logo-flip-front" style="display:none"></span>
          <div class="lw-cover-body">
            <div class="lw-cover-info">
              <span class="txt">See today's offer</span>
              <span class="via">via Lulu Ads</span>
            </div>
            <div class="lw-cover-ctarow"><span class="cta">Tap to reveal <span class="lw-flip-arrow">→</span></span></div>
          </div>
        </div>
      </div>
      <div class="lw-strip" id="strip-back">
        <div class="lw-cover-card-inner" id="back-inner">
          <div class="lw-cover" id="sp-cover-flip">
            <span class="badge lw-cover-badge">SPONSORED</span>
          </div>
          <span class="lw-logo lw-cover-logo" id="sp-logo-flip" style="display:none"></span>
          <div class="lw-cover-body">
            <div class="lw-cover-info">
              <span class="txt" id="sp-text-flip"></span>
              <span class="via">via Lulu Ads</span>
            </div>
            <div class="lw-cover-ctarow"><span class="cta" id="sp-cta-flip">Learn more →</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>

<script>
(function () {
  "use strict";
  var TEMPLATE = "__LW_TEMPLATE__";
  var SPONSOR_TEMPLATE = "__LW_SPONSOR_TEMPLATE__";
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
  /* Fills one strip instance's logo tile -- shared by the default "card"
     strip (#sp-logo/#sp-text/#sp-cta) and flip-card's back face (#sp-logo-
     flip/#sp-text-flip/#sp-cta-flip), so both presentations get the exact
     same logo/letter-tile-fallback behavior from one implementation. */
  function fillLogo(logo, brandWord, s) {
    // Preserves any class NOT owned by this function (e.g. "lw-cover-logo",
    // which positions the overlap) across a full className reassignment --
    // without this, a real logo's async img.onload firing would silently
    // wipe whatever a caller added beforehand.
    var extra = logo.className.split(/\s+/).filter(function (c) {
      return c && c !== "lw-logo" && c !== "fallback";
    }).join(" ");
    function withExtra(base) { return extra ? base + " " + extra : base; }

    function letterTile() {
      logo.textContent = (brandWord.charAt(0) || "•").toUpperCase();
      logo.className = withExtra("lw-logo fallback");
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
      img.onload = function () { logo.textContent = ""; logo.className = withExtra("lw-logo"); logo.style.background = "#fff"; logo.appendChild(img); logo.style.display = "flex"; };
      img.onerror = letterTile;
      img.src = logoUrl;
    } else {
      letterTile();
    }
  }

  /* Cover band background: a real sponsor image when the live payload
     supplies one (forward-compatible with the ads-server adding
     cover_image_url/coverImageUrl alongside logo_url someday, same
     snake/camelCase acceptance), the animated gradient otherwise. Unlike
     `logo`/`accent`/`template` in the standalone widget, this is NOT a
     registration-time integrator param -- the cover is the sponsor's own
     creative, so it has to travel with the rest of the live per-call
     sponsored payload, same as logo_url already does. */
  function setCoverImage(cover, s) {
    var url = (typeof s.cover_image_url === "string" && s.cover_image_url) ? s.cover_image_url
      : (typeof s.coverImageUrl === "string" ? s.coverImageUrl : "");
    if (url) {
      cover.style.backgroundImage = "url(" + JSON.stringify(url) + ")";
      cover.classList.add("has-image");
    } else {
      cover.style.backgroundImage = "";
      cover.classList.remove("has-image");
    }
  }

  function fireImpressionBeacon(el, s) {
    /* Rendered-impression beacon: fires exactly when the strip (or, for
       flip-card, its front-face teaser) becomes visible -- never on mere
       API output -- so CPM counts what a human actually saw. The
       disclosure ("Sponsored") is what's visible at that moment for both
       presentations, so both fire here, not gated on flip-card's reveal
       interaction. Fire-and-forget; a blocked/failed pixel changes
       nothing visually. */
    var impUrl = (typeof s.imp_url === "string" && s.imp_url) ? s.imp_url
      : (typeof s.impUrl === "string" ? s.impUrl : "");
    if (impUrl && !el.dataset.impFired) {
      el.dataset.impFired = "1";
      var px = new Image(1, 1);
      px.src = impUrl;
    }
  }

  function renderSponsored(sc) {
    var s = sc && sc.sponsored;
    if (!s || typeof s.text !== "string" || typeof s.url !== "string" || !s.text || !s.url) return;
    var brandWord = (s.text.match(/[A-Za-z0-9][\w.\-]*/) || [""])[0];

    if (SPONSOR_TEMPLATE === "flip-card") {
      document.getElementById("sp-text-flip").textContent = s.text;
      fillLogo(document.getElementById("sp-logo-flip"), brandWord, s);
      fillLogo(document.getElementById("sp-logo-flip-front"), brandWord, s);
      setCoverImage(document.getElementById("sp-cover-flip"), s);
      setCoverImage(document.getElementById("sp-cover-flip-front"), s);
      var flip = document.getElementById("strip-flip");
      var frontInner = document.getElementById("front-inner");
      var backInner = document.getElementById("back-inner");
      flip.classList.add("show");
      // Both faces (.lw-strip-front / #strip-back) are position:absolute;
      // inset:0 (pure crossfade, no layout shift) -- which means each
      // face's OWN offsetHeight just reflects that fixed box, never its
      // content's natural height. Their actual cover-card layout lives
      // one level deeper in a normal-flow .lw-cover-card-inner child
      // (#front-inner / #back-inner); THAT child's offsetHeight is what
      // reflects true content height, measurable even while its
      // absolutely-positioned parent is at opacity:0 (layout still
      // happens, only painting is suppressed), so this works before the
      // very first flip too, not just after.
      flip.style.height = frontInner.offsetHeight + "px";
      fireImpressionBeacon(flip, s);
      // First click flips to reveal the real offer (back face); once
      // flipped, the back face IS the offer -- a further click opens it,
      // matching every other template's "click the offer to follow it"
      // contract instead of trapping the user in a flip loop.
      flip.addEventListener("click", function () {
        if (flip.classList.contains("flipped")) {
          openLink(s.url);
        } else {
          flip.classList.add("flipped");
          flip.style.height = backInner.offsetHeight + "px";
          sizeChanged();
        }
      });
      return;
    }

    if (SPONSOR_TEMPLATE === "carousel") {
      document.getElementById("sp-text-carousel").textContent = s.text;
      fillLogo(document.getElementById("sp-logo-carousel"), brandWord, s);
      fillLogo(document.getElementById("sp-logo-carousel-big"), brandWord, s);
      setCoverImage(document.getElementById("sp-cover-carousel"), s);
      var carStrip = document.getElementById("strip-carousel");
      carStrip.classList.add("show");
      fireImpressionBeacon(carStrip, s);
      // All three slides are the SAME offer -- clicking navigates
      // identically regardless of which slide is currently showing.
      carStrip.addEventListener("click", function () { openLink(s.url); });
      startCarousel();
      return;
    }

    // "card" and "scratch-reveal" share the exact same populated strip --
    // content visible immediately, never gated -- scratch-reveal only
    // adds a canvas layer on TOP of it.
    document.getElementById("sp-text").textContent = s.text;
    var logo = document.getElementById("sp-logo");
    fillLogo(logo, brandWord, s);
    setCoverImage(document.getElementById("sp-cover"), s);
    var strip = document.getElementById("strip");
    strip.classList.add("show");
    fireImpressionBeacon(strip, s);
    strip.addEventListener("click", function () { openLink(s.url); });

    if (SPONSOR_TEMPLATE === "scratch-reveal") {
      setupScratchReveal(document.getElementById("sp-body"));
    }
  }

  var CAROUSEL_SLIDE_MS = 2200;
  var CAROUSEL_SLIDE_COUNT = 3; // big logo, offer text, CTA
  var CAROUSEL_STEPS = 7; // brand -> offer -> CTA -> brand -> offer -> CTA -> (settle)

  // Auto-advances #carousel-track through its three slides (brand
  // headline, offer text, CTA) for a couple of full passes, then stops on
  // the CTA slide -- reaching for the actionable slide, not looping
  // forever inside someone else's UI. All three slides are the same
  // offer/link (see the click handler in renderSponsored), so there is
  // nothing to gate: this reorders framing, never content.
  function startCarousel() {
    var track = document.getElementById("carousel-track");
    var dots = document.querySelectorAll("#carousel-dots .lw-dot");
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return; // stays on slide 0
    function show(slide) {
      track.style.transform = "translateX(-" + slide * 100 + "%)";
      dots.forEach(function (d, di) { d.classList.toggle("on", di === slide); });
    }
    var i = 0;
    var timer = setInterval(function () {
      i++;
      if (i >= CAROUSEL_STEPS) {
        clearInterval(timer);
        show(2); // always finish pointed at the CTA slide (index 2)
        return;
      }
      show(i % CAROUSEL_SLIDE_COUNT);
    }, CAROUSEL_SLIDE_MS);
  }

  var SCRATCH_AUTO_REVEAL_MS = 5000;
  var SCRATCH_CLEAR_THRESHOLD = 0.55;

  // `zone` is .lw-cover-body ONLY -- never the whole strip, which also
  // contains .lw-cover (logo + "SPONSORED" disclosure). The canvas must
  // never cover disclosure.
  function setupScratchReveal(zone) {
    var canvas = document.getElementById("scratch-canvas");
    var ctx = canvas.getContext && canvas.getContext("2d");
    if (!ctx) return; // no canvas support -- offer is already fully visible above, fail open
    var rect = zone.getBoundingClientRect();
    canvas.width = rect.width || zone.offsetWidth;
    canvas.height = rect.height || zone.offsetHeight;
    canvas.style.display = "block";

    // Lottery-ticket foil look: gold metallic gradient, diagonal hatch
    // texture, a dashed perforation (like a real ticket stub edge), a
    // ticket glyph, and bold copy -- reads as a physical scratch ticket
    // at a glance. Still just decoration over a guaranteed reveal: no
    // "you win/you lose" copy anywhere, since there is only one outcome.
    ctx.globalCompositeOperation = "source-over";
    var grad = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
    grad.addColorStop(0, "#f3d98a");
    grad.addColorStop(.5, "#d9ad4e");
    grad.addColorStop(1, "#b8863a");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = "rgba(255,255,255,.28)";
    ctx.lineWidth = 3;
    for (var x = -canvas.height; x < canvas.width; x += 9) {
      ctx.beginPath();
      ctx.moveTo(x, canvas.height);
      ctx.lineTo(x + canvas.height, 0);
      ctx.stroke();
    }

    // A stub perforation near the left edge, like tearing a ticket stub.
    var stubX = Math.min(46, canvas.width * 0.16);
    ctx.strokeStyle = "rgba(80,58,20,.5)";
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 5]);
    ctx.beginPath();
    ctx.moveTo(stubX, 4);
    ctx.lineTo(stubX, canvas.height - 4);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = "rgba(60,42,14,.7)";
    ctx.font = "20px -apple-system, BlinkMacSystemFont, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("\u{1F3AB}", stubX / 2, canvas.height / 2 + 7);

    var textX = stubX + (canvas.width - stubX) / 2;
    ctx.fillStyle = "rgba(50,35,10,.9)";
    ctx.font = "800 12.5px -apple-system, BlinkMacSystemFont, sans-serif";
    ctx.fillText("SCRATCH TO REVEAL", textX, canvas.height / 2 - 2);
    ctx.fillStyle = "rgba(50,35,10,.65)";
    ctx.font = "600 10.5px -apple-system, BlinkMacSystemFont, sans-serif";
    ctx.fillText("your offer is ready", textX, canvas.height / 2 + 15);

    var scratching = false, cleared = 0, revealed = false;
    var totalPixels = canvas.width * canvas.height;

    function reveal() {
      if (revealed) return;
      revealed = true;
      canvas.style.display = "none";
    }
    function scratchAt(x, y) {
      ctx.globalCompositeOperation = "destination-out";
      ctx.beginPath();
      ctx.arc(x, y, 22, 0, Math.PI * 2);
      ctx.fill();
      cleared += Math.PI * 22 * 22;
      if (cleared / totalPixels > SCRATCH_CLEAR_THRESHOLD) reveal();
    }
    function posFromEvent(e) {
      var r = canvas.getBoundingClientRect();
      var p = e.touches ? e.touches[0] : e;
      return { x: p.clientX - r.left, y: p.clientY - r.top };
    }
    canvas.addEventListener("pointerdown", function (e) {
      scratching = true;
      var p = posFromEvent(e);
      scratchAt(p.x, p.y);
    });
    canvas.addEventListener("pointermove", function (e) {
      if (!scratching) return;
      var p = posFromEvent(e);
      scratchAt(p.x, p.y);
    });
    window.addEventListener("pointerup", function () { scratching = false; });
    // `strip` itself is one big click-to-navigate target (see
    // renderSponsored above) -- without this, a scratch tap's own
    // click event would bubble straight through the canvas to that
    // handler and navigate away before anything was ever revealed.
    // Stops mattering once revealed: the canvas is hidden by then, so
    // it's no longer in the click path at all.
    canvas.addEventListener("click", function (e) {
      if (!revealed) e.stopPropagation();
    });

    // Binding guardrail: reveal is guaranteed regardless of interaction --
    // this is a reveal ANIMATION, never gated content. The offer underneath
    // is already fully rendered and click-through works on it the whole
    // time (the canvas only visually covers it, .lw-strip's own click
    // handler is on `strip`, not the canvas, so scratching never blocks it).
    setTimeout(reveal, SCRATCH_AUTO_REVEAL_MS);
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
    sponsor_template: str = "card",
) -> str:
    """Builds the self-contained widget HTML for one tool: the shared frame
    with this tool's template + mapping substituted in. Exposed separately
    from registration for tests and snapshotting.

    `sponsor_template` picks the SPONSORED strip's own visual format (see
    `SPONSOR_TEMPLATES`) -- independent of `template`, which is this
    result widget's own body layout. Raises `ValueError` on an
    unrecognized value, same shape as `template`'s own validation.
    """
    if template not in TEMPLATES:
        raise ValueError(
            f"unknown template {template!r} -- expected one of {', '.join(TEMPLATES)}"
        )
    if sponsor_template not in SPONSOR_TEMPLATES:
        raise ValueError(
            f"unknown sponsor_template {sponsor_template!r} -- expected one of {', '.join(SPONSOR_TEMPLATES)}"
        )
    config: dict = {"mapping": mapping or {}}
    if body_html:
        config["bodyHtml"] = body_html
    config_json = json.dumps(config, separators=(",", ":"), ensure_ascii=False)
    return (
        FRAME_HTML
        .replace(_CONFIG_PLACEHOLDER, _escape_html(config_json))
        .replace(_TEMPLATE_PLACEHOLDER, template)
        .replace(_SPONSOR_TEMPLATE_PLACEHOLDER, sponsor_template)
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
    sponsor_template: str = "card",
):
    """Registers a predefined result widget for ``tool`` and attaches it.

    Call AFTER the tool is registered (module import order: define your
    ``@mcp.tool`` functions, then call this) -- the tool's MCP Apps config
    is patched in place, deliberately overriding ``enable_lulu_ads``'s
    generic sponsored-card widget for this tool. The sponsored DATA field
    still flows from the middleware and renders inside this widget as the
    disclosed strip -- ``sponsor_template`` picks that strip's own visual
    format from ``SPONSOR_TEMPLATES`` (independent of ``template``, this
    widget's own body layout); defaults to ``"card"``, the original
    always-visible strip every existing integrator already gets.

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
    html = result_widget_html(
        template=template, mapping=mapping, body_html=body_html, sponsor_template=sponsor_template,
    )

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
    #
    # CopilotKit's MCPAppsMiddleware (@ag-ui/mcp-apps-middleware@0.0.3) uses
    # a third dialect: it only recognizes a tool as UI-capable via a FLAT
    # `_meta["ui/resourceUri"]` string key (its discovery filter is
    # `typeof tool._meta?.["ui/resourceUri"] == "string"`), and never looks
    # at the nested `ui.resourceUri` above. Verified 2026-08-25 against the
    # real compiled middleware: without this flat key, zero tools are
    # injected into the agent and no widget is ever attempted, before any
    # rendering/CSP logic runs. Purely additive alongside the two existing
    # keys — Claude and ChatGPT already ignore each other's dialect key the
    # same way, so this doesn't change either of their paths.
    import asyncio

    _openai_csp = {
        "connect_domains": ["https://ads.getlulu.dev"],
        "resource_domains": ["https://ads.getlulu.dev"],
    }
    ui_meta = {
        "ui": {"resourceUri": uri, "visibility": visibility or ["model"]},
        "openai/outputTemplate": uri,
        "ui/resourceUri": uri,
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
