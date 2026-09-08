# Per-Ad Template Live Override — Design

## Problem

LUL-64 (in the separate `kin` repo) wired the admin-selectable `ads.ad_format` column all the way to `/slot`'s JSON response as a `template` field. But nothing consumes it: the published `lulu-ads` SDK's response parsers (`client.py`'s `_parse()`, `index.ts`'s `sponsoredSlot()`) both drop unrecognized keys, and the widget bundle (`js/widget-src/`) only ever reads `template` from the registration-time static opts blob (`register_sponsored_widget(template=...)`, baked into the compiled HTML once, per LUL-46). Result: an admin can set an ad's template in `/admin/campaigns`, but every host renders that ad using whatever template the integrator happened to register with at startup — usually `"card"` — regardless.

## Goal

An ad's `/slot`-reported `template` should actually control which component the widget renders, on a per-call basis, for every host that already supports the live sponsored-widget system.

## Precedence rule (decided)

**Per-ad wins.** If `/slot`'s live response carries a recognized `template`, the widget renders that. If it's absent, unrecognized, or the live tool-result never arrives, the widget falls back to the registration-time `template=` the integrator set. If that's also absent/unrecognized, it falls back to `"card"`.

Rationale: an admin explicitly picking a template for *this* ad is a more specific, more recent, more intentional signal than a blanket default an integrator set once, months ago, at server startup. The alternative (registration-time always wins) would make the `/admin/campaigns` control silently do nothing for any host whose integrator ever set a `template=`, which is most of them going forward — that defeats the point of building it.

## Why this is small, not a rewrite

The mechanism this change extends **already exists and is already load-bearing** for every template shipped so far — it isn't new infrastructure:

- A fresh iframe is created per tool call already (protocol-level, not something we control or need to change).
- That iframe starts in a loading skeleton and renders real ad content only once the host relays a live `ui/notifications/tool-result` message — this is how `imp_url` and `logo_url` already flow from `/slot` to the render, verified live in production (LUL-71's rendered-impression beacon).
- No integrator code changes are required for those two fields, and none will be required for `template` either: every integration point found (`demo-flights-mcp/server.py`'s manual override, and the auto-injecting `LuluAdsMiddleware`) does `result["sponsored"] = <sdk's returned dict>` — whatever keys the SDK includes automatically ride the existing wire.

So this is "thread one more field through an already-working, already-fail-open channel," not "build new plumbing."

## Changes

Four files, all additive, no breaking changes to any current consumer:

### 1. `python/lulu_ads/client.py` — `_parse()` (~line 201-215)

```python
def _parse(status_code: int, json_body) -> dict | None:
    if status_code != 200 or not isinstance(json_body, dict):
        return None
    text, url = json_body.get("text"), json_body.get("url")
    if not text or not url:
        return None
    result = {"label": "Sponsored", "text": str(text), "url": str(url)}
    if json_body.get("logo_url"):
        result["logo_url"] = str(json_body["logo_url"])
    if json_body.get("imp_url"):
        result["imp_url"] = str(json_body["imp_url"])
    if json_body.get("template"):
        # Per-ad template (LUL-64's ad_format, forwarded by ads-server's
        # /slot as "template") -- rides the same wire path imp_url/logo_url
        # already use. The widget bundle prefers this live value over
        # whatever template= the integrator registered with; falls back to
        # "card" client-side if it's not a template this bundle build
        # recognizes. See docs/superpowers/specs/2026-09-07-per-ad-template-live-override-design.md.
        result["template"] = str(json_body["template"])
    return result
```

### 2. `js/src/index.ts` — `Sponsored` interface + `sponsoredSlot()` (~line 24, ~line 221)

Add `template?: string` to the `Sponsored` interface, and forward `body.template` into `result.template` the same way `logoUrl`/`impUrl` are already forwarded (same `if (body.x) result.x = String(body.x)` shape).

### 3. `js/widget-src/src/mcpBridge.ts` — `RawSponsored`, `SponsoredData`, `extractSponsored()`

Add `template?: unknown` to `RawSponsored`, `template?: string` to `SponsoredData`, and in `extractSponsored()` forward it the same way `logo_url`/`imp_url` are handled (string-typed, absent-if-not-a-string).

### 4. `js/widget-src/src/SponsoredCard.tsx` — `SponsoredCardState`'s `"loaded"` variant

Add `template?: string` to the `"loaded"` branch (mirrors `SponsoredData`, same as `impUrl` already does — the comment there already explains why: "carried on state only because it's spread in from `SponsoredData`").

### 5. `js/widget-src/src/App.tsx` — component selection (~line 76)

```tsx
// before:
const Content = TEMPLATES[initialOptions?.template ?? "card"] ?? SponsoredCard

// after:
const pick = (name?: string) =>
  name && Object.prototype.hasOwnProperty.call(TEMPLATES, name) ? TEMPLATES[name] : undefined
const liveTemplate = state.kind === "loaded" ? state.template : undefined
const Content = pick(liveTemplate) ?? pick(initialOptions?.template) ?? SponsoredCard
```

`Content` already recomputes on every render (it's not memoized), so once `state` transitions to `"loaded"` with a live `template`, the next render picks it up automatically. Note this is a two-tier fallback, not a single `??` chain: a plain `TEMPLATES[liveTemplate ?? initialOptions?.template ?? "card"] ?? SponsoredCard` would be wrong, because `??` only checks nullishness — an unrecognized-but-present live value (not null/undefined) would short-circuit the chain and skip the registration-time default entirely, landing straight on `SponsoredCard` instead of honoring what the integrator registered. `pick()` instead checks recognition explicitly at each tier (recognized live wins → else the registration-time default → else `SponsoredCard`), matching the "Precedence rule (decided)" section above.

`pick()` also guards with `Object.prototype.hasOwnProperty` rather than a plain truthy/presence check at either tier: `TEMPLATES` is a plain object literal, so a bracket lookup for a prototype-chain name like `"constructor"` or `"toString"` resolves through `Object.prototype` to a real, truthy value — which would otherwise be misread as "recognized" even though it isn't a template. This matters specifically for the live tier: the registration-time value is validated server-side before this code ever runs (`register_sponsored_widget()` raises on an unrecognized name), but the live value is admin-set, external data relayed from `/slot` with no server-side allowlist by design — this is the first path where a prototype-chain name is reachable from live, untrusted input. Left unguarded, a crafted/buggy `"constructor"` live value would cause React to throw or render nothing, after the rendered-impression beacon (which fires on the loading→loaded transition, before that failure is visible) had already fired — billing a CPM for an ad that never rendered.

This is what makes it safe for `/slot` to pass through a template the bundle doesn't know about yet (e.g. `"comparison"` while LUL-50 is mid-flight) without ads-server needing its own allowlist, per LUL-64's design — an unrecognized live value degrades to the registration-time default, not past it, and a prototype-chain name is never treated as recognized at either tier.

## Backward compatibility

Fully additive on every layer:
- An older, already-published SDK version ignores the new `template` field in `/slot`'s response (unknown key), exactly as it does today.
- A `/slot` response without a `template` field (shouldn't happen post-LUL-64, but defensively) leaves `result` without the key, same as `logo_url`/`imp_url`'s existing optional pattern.
- A host that never relays live `tool-result` (the one already-known, already-documented gap — see `mcpBridge.ts`'s own comment) simply never gets a live template override; it renders whatever the registration-time default was, exactly as it does today for every other live field.
- No existing integrator has to change a line of code for this to reach their widget once they upgrade the SDK version.

## Testing

Mirror the existing test files for each changed module (`python/tests/test_client.py`, `js/test/client.test.ts`, `js/widget-src/src/mcpBridge.test.ts`, `js/widget-src/src/App.test.tsx`) — add cases for: `template` present and recognized → forwarded/rendered; absent → falls back to registration-time default; present but not a key in `TEMPLATES` (including a prototype-chain name like `"constructor"`, which `pick()`'s own-property check must also treat as unrecognized) → falls back to registration-time default, then to `"card"` (not a crash, not a silent skip to `"card"` past the registration-time default). No existing test should need to change except where it asserts an exact dict/object shape that gains an optional key (same class of update LUL-71's `imp_url` rollout required).

## Release

Bump `lulu-ads` on both PyPI and npm (patch or minor — additive, no breaking change). Rebuild the widget bundle via the existing `scripts/sync-widget-bundle.sh` pattern (same release step LUL-46/47/50 already used) so `_generated_widget_bundle.py` / `generatedWidgetBundle.ts` pick up the `App.tsx`/`mcpBridge.ts` changes.

## Out of scope

- Nothing in `ads-server` or the `kin` repo changes — `/slot` already carries `template` correctly (LUL-64), unmodified here.
- No change to `register_sponsored_widget()`'s registration-time `template=` parameter or validation — it remains the fallback default, exactly as documented.
- The known host-relay gap ("a real, currently-unaddressed gap" per `mcpBridge.ts`'s own comment, for hosts that never push `tool-result`) is pre-existing and unaffected by this change — this change doesn't make it better or worse, since a host with that gap already never showed live ad content of any kind.
