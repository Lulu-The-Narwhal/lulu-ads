# Per-Ad Template Live Override Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an ad's `/slot`-reported `template` field actually control which sponsor-widget component renders, per call, on every host that already supports the live tool-result system — without breaking any existing, already-published SDK consumer.

**Architecture:** Thread `template` through the same already-working channel `imp_url`/`logo_url` already use: `/slot`'s JSON response → SDK's `_parse()`/`sponsoredSlot()` → integrator's `structuredContent.sponsored` (zero integrator code change) → the widget iframe's live `ui/notifications/tool-result` handler → `App.tsx`'s component selection. Live value wins; registration-time `template=` is the fallback; `"card"` is the final floor.

**Tech Stack:** Python 3.10+ (`httpx`, `pytest`/`pytest-asyncio`), TypeScript (`vitest`), React 19 (widget bundle, `js/widget-src/`).

**Spec:** `docs/superpowers/specs/2026-09-07-per-ad-template-live-override-design.md`

## Global Constraints

- **Precedence, exact:** live `template` (from the current call's `tool-result`) wins if present and recognized by this bundle build → else registration-time `template=` (the static, per-integrator default) → else `"card"`. Never anything else, never a crash on an unrecognized value.
- **Zero integrator code changes.** Every change in this plan lives inside the `lulu-ads` package itself (both languages) and the compiled widget bundle. No repo outside `lulu-ads` is touched.
- **Fully additive.** No existing test's assertions change except where they assert an *exact* object/dict shape that gains a new optional key — and even those only change if the test's fixture actually includes a `template` value (most won't, since `template` is optional and omitted-when-absent, matching `logo_url`/`imp_url`'s existing pattern).
- Keep the Python and TypeScript sides byte-for-byte parallel, per this repo's established convention (`widget.py`'s own module docstring: "Port of js/src/widget.ts — keep both in sync").
- This plan does not touch `register_sponsored_widget()`/`registerSponsoredWidget()`'s registration-time validation or defaults — those stay exactly as documented.

---

### Task 1: `python/lulu_ads/client.py` — forward `template` in `_parse()`

**Files:**
- Modify: `python/lulu_ads/client.py:201-215` (`_parse()`)
- Test: `python/tests/test_client.py`

**Interfaces:**
- Consumes: `/slot`'s JSON response (already includes `template`, unmodified by this plan — see LUL-64 in the `kin` repo).
- Produces: `sponsored_slot()`/`sponsored_slot_sync()`'s returned dict now optionally carries a `"template"` key (`str`), same optionality pattern as the existing `"logo_url"`/`"imp_url"` keys — present only when `/slot`'s response has a truthy `template` value.

- [ ] **Step 1: Write the failing tests**

Add to `python/tests/test_client.py`, near the existing `test_logo_url_*` tests:

```python
async def test_template_passed_through_when_present():
    with_template = dict(GOOD, template="banner")
    ads = make_client(lambda r: httpx.Response(200, json=with_template))
    out = await ads.sponsored_slot(context={"tool": "x"})
    assert out["template"] == "banner"


async def test_template_absent_when_not_in_response():
    ads = make_client(lambda r: httpx.Response(200, json=GOOD))
    out = await ads.sponsored_slot(context={"tool": "x"})
    assert "template" not in out
```

- [ ] **Step 2: Set up the environment and run tests to verify they fail**

From `python/`:
```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest tests/test_client.py -v -k template
```
Expected: both new tests FAIL with `KeyError: 'template'`

- [ ] **Step 3: Implement**

In `python/lulu_ads/client.py`, modify `_parse()`:

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
        # Rendered-impression beacon: widget frames fire this as a 1px img
        # the moment the sponsored strip actually shows, so "rendered" is
        # counted separately from "returned" (CPM only ever pays rendered).
        result["imp_url"] = str(json_body["imp_url"])
    if json_body.get("template"):
        # Per-ad template (kin repo's LUL-64: ads.ad_format, forwarded by
        # ads-server's /slot as "template") -- rides the same wire path
        # imp_url/logo_url already use. The widget bundle prefers this
        # live value over whatever template= the integrator registered
        # with; falls back to "card" client-side if it's not a template
        # this bundle build recognizes. See docs/superpowers/specs/
        # 2026-09-07-per-ad-template-live-override-design.md.
        result["template"] = str(json_body["template"])
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_client.py -v
```
Expected: all PASS, including the two new ones

- [ ] **Step 5: Commit**

```bash
git add python/lulu_ads/client.py python/tests/test_client.py
git commit -m "feat(client): forward template through _parse()"
```

---

### Task 2: `js/src/index.ts` — forward `template` in `sponsoredSlot()`

**Files:**
- Modify: `js/src/index.ts:24-32` (`Sponsored` interface), `js/src/index.ts:195-227` (`sponsoredSlot()`)
- Test: `js/test/client.test.ts`

**Interfaces:**
- Consumes: `/slot`'s JSON response, same as Task 1.
- Produces: `Sponsored` interface gains `template?: string`; `sponsoredSlot()`'s returned object optionally carries `.template`, same optionality as `.logoUrl`/`.impUrl`.

- [ ] **Step 1: Write the failing tests**

Add to `js/test/client.test.ts`, near the existing `logoUrl` tests:

```typescript
test("template present when the response has one", async () => {
  mockFetch(async () => new Response(JSON.stringify({ ...GOOD, template: "banner" }), { status: 200 }));
  const out = await ads().sponsoredSlot({ context: { tool: "x" } });
  expect(out?.template).toBe("banner");
});

test("template absent when the response has none", async () => {
  mockFetch(async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const out = await ads().sponsoredSlot({ context: { tool: "x" } });
  expect(out).not.toHaveProperty("template");
});
```

- [ ] **Step 2: Run tests to verify they fail**

From `js/`:
```bash
npm install
npx vitest run test/client.test.ts -t template
```
Expected: both new tests FAIL (`out?.template` is `undefined`, `toBe("banner")` fails)

- [ ] **Step 3: Implement**

In `js/src/index.ts`, modify the `Sponsored` interface:

```typescript
export interface Sponsored {
  label: "Sponsored";
  text: string;
  url: string;
  logoUrl?: string;
  /** Rendered-impression beacon — the widget frame fires this as a 1px img
   * the moment the sponsored strip actually shows (CPM counts rendered,
   * never merely returned). */
  impUrl?: string;
  /** Per-ad template (kin repo's LUL-64) — the widget bundle prefers this
   * live value over whatever template= the integrator registered with.
   * See docs/superpowers/specs/2026-09-07-per-ad-template-live-override-design.md. */
  template?: string;
}
```

And in `sponsoredSlot()`'s body parsing (find the block that builds `result` from `body.logo_url`/`body.imp_url`):

```typescript
      const body = (await res.json()) as { text?: unknown; url?: unknown; logo_url?: unknown; imp_url?: unknown; template?: unknown };
      if (!body?.text || !body?.url) return null;
      const result: Sponsored = { label: "Sponsored", text: String(body.text), url: String(body.url) };
      if (body.logo_url) result.logoUrl = String(body.logo_url);
      if (body.imp_url) result.impUrl = String(body.imp_url);
      if (body.template) result.template = String(body.template);
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx vitest run test/client.test.ts
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add js/src/index.ts js/test/client.test.ts
git commit -m "feat(client): forward template through sponsoredSlot()"
```

---

### Task 3: `js/widget-src/src/mcpBridge.ts` — read `template` from the live payload

**Files:**
- Modify: `js/widget-src/src/mcpBridge.ts` (`RawSponsored` interface, `SponsoredData` interface, `extractSponsored()`)
- Test: `js/widget-src/src/mcpBridge.test.ts`

**Interfaces:**
- Consumes: `structuredContent.sponsored.template` from a live `ui/notifications/tool-result` message.
- Produces: `SponsoredData` gains `template?: string`, populated by `extractSponsored()` — consumed by Task 4 (`SponsoredCardState`) and Task 5 (`App.tsx`).

- [ ] **Step 1: Write the failing tests**

Add to `js/widget-src/src/mcpBridge.test.ts`, inside the existing `describe("extractSponsored", ...)` block, near the `logoDataUri`/`impUrl` tests:

```typescript
  it("reads template from the live payload", () => {
    const msg = toolResultMessage({ text: "hi", url: "https://x.example", template: "banner" })
    expect(extractSponsored(msg)?.template).toBe("banner")
  })

  it("omits template when the live payload has none", () => {
    const msg = toolResultMessage({ text: "hi", url: "https://x.example" })
    expect(extractSponsored(msg)?.template).toBeUndefined()
  })
```

- [ ] **Step 2: Run tests to verify they fail**

From `js/widget-src/`:
```bash
npm install
npx vitest run src/mcpBridge.test.ts -t template
```
Expected: both new tests FAIL (`extractSponsored(msg)?.template` is `undefined` for the first test too, since the field isn't read yet)

- [ ] **Step 3: Implement**

In `js/widget-src/src/mcpBridge.ts`:

1. Add `template?: unknown` to the `RawSponsored` interface (alongside `logo_url`/`imp_url`):

```typescript
interface RawSponsored {
  label?: unknown
  text?: unknown
  url?: unknown
  logo_url?: unknown
  logoUrl?: unknown
  imp_url?: unknown
  impUrl?: unknown
  template?: unknown
}
```

2. Add `template?: string` to the `SponsoredData` interface:

```typescript
export interface SponsoredData {
  label: string
  text: string
  url: string
  logoDataUri?: string
  cta: string
  impUrl?: string
  /** Per-ad template (kin repo's LUL-64) — read from the live tool-result
   * payload; App.tsx prefers this over the registration-time default.
   * See docs/superpowers/specs/2026-09-07-per-ad-template-live-override-design.md. */
  template?: string
}
```

3. In `extractSponsored()`, right before the `return { label, text, url, logoDataUri, cta, impUrl }` line, add:

```typescript
  const template =
    typeof sponsored.template === "string" && sponsored.template
      ? sponsored.template
      : undefined

  return { label, text, url, logoDataUri, cta, impUrl, template }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx vitest run src/mcpBridge.test.ts
```
Expected: all PASS. Confirm the existing exact-shape test at the top of `describe("extractSponsored", ...)` (`expect(extractSponsored(msg)).toEqual({label, text, url, logoDataUri, cta})`) still passes — its fixture never sets `template`, so `extractSponsored` returns `template: undefined`, which `toEqual` treats as equivalent to the key being absent.

- [ ] **Step 5: Commit**

```bash
git add js/widget-src/src/mcpBridge.ts js/widget-src/src/mcpBridge.test.ts
git commit -m "feat(widget): read template from the live tool-result payload"
```

---

### Task 4: `js/widget-src/src/SponsoredCard.tsx` — carry `template` on `SponsoredCardState`

**Files:**
- Modify: `js/widget-src/src/SponsoredCard.tsx:21-35` (`SponsoredCardState` type)

**Interfaces:**
- Consumes: nothing new (this is a type-only change).
- Produces: `SponsoredCardState`'s `"loaded"` variant gains `template?: string`, matching `SponsoredData` — consumed by Task 5 (`App.tsx`).

No test for this task — it's a type-only addition to an existing discriminated union, mirroring exactly how `impUrl` was already added to this same type (see the existing `impUrl` field's own comment in this type for precedent). Task 5's tests exercise the actual behavior this type change enables.

- [ ] **Step 1: Implement**

In `js/widget-src/src/SponsoredCard.tsx`, modify the `"loaded"` branch of `SponsoredCardState`:

```typescript
export type SponsoredCardState =
  | { kind: "loading" }
  | {
      kind: "loaded"
      label: string
      text: string
      url: string
      logoDataUri?: string
      cta: string
      /** Rendered-impression beacon URL (LUL-71) -- not rendered by any
       * template component itself; App.tsx fires it once, centrally, on
       * this "loaded" transition. Carried on state only because it's
       * spread in from `SponsoredData` alongside everything else. */
      impUrl?: string
      /** Per-ad template (kin repo's LUL-64) -- not rendered by any
       * template component itself; App.tsx reads this to pick WHICH
       * component to render. Carried on state only because it's spread
       * in from `SponsoredData` alongside everything else, same as
       * impUrl above. */
      template?: string
    }
  | { kind: "noFill" }
```

- [ ] **Step 2: Type-check**

From `js/widget-src/`:
```bash
npx tsc --noEmit -p .
```
Expected: no new errors (this is a widening change — an optional field addition to a type — so nothing that compiled before should break)

- [ ] **Step 3: Commit**

```bash
git add js/widget-src/src/SponsoredCard.tsx
git commit -m "feat(widget): add template to SponsoredCardState"
```

---

### Task 5: `js/widget-src/src/App.tsx` — live template wins over registration-time

**Files:**
- Modify: `js/widget-src/src/App.tsx:76` (`Content` component selection)
- Test: `js/widget-src/src/App.test.tsx`

**Interfaces:**
- Consumes: `SponsoredCardState`'s `template` field (Task 4), `SponsoredData.template` via `state` (Task 3).
- Produces: the widget's rendered component now follows the precedence rule from Global Constraints.

- [ ] **Step 1: Write the failing tests**

Add to `js/widget-src/src/App.test.tsx`, inside the existing `describe("App: template dispatch", ...)` block, after the existing tests:

```typescript
  it("live template overrides the registration-time default", async () => {
    setOpts({ text: "x", url: "https://x.com", template: "card" })
    await renderWithToolResult({ text: "Save 15%", url: "https://example.com", template: "banner" })
    expect(container.querySelector("span")?.textContent).toBe("Sponsored")
  })

  it("falls back to the registration-time default when the live payload has no template", async () => {
    setOpts({ text: "x", url: "https://x.com", template: "banner" })
    await renderWithToolResult({ text: "Save 15%", url: "https://example.com" })
    expect(container.querySelector("span")?.textContent).toBe("Sponsored")
  })

  it("falls back to the registration-time default when the live template is unrecognized", async () => {
    setOpts({ text: "x", url: "https://x.com", template: "banner" })
    await renderWithToolResult({ text: "Save 15%", url: "https://example.com", template: "does-not-exist" })
    expect(container.querySelector("span")?.textContent).toBe("Sponsored")
  })
```

- [ ] **Step 2: Run tests to verify they fail**

From `js/widget-src/`:
```bash
npx vitest run src/App.test.tsx -t "template dispatch"
```
Expected: the first new test FAILS (renders SponsoredCard per the registration-time `"card"` default, no `<span>`, since `Content` doesn't yet read the live value) — the other two should already pass by coincidence (they don't need the new behavior), confirm that with the run, then focus on the first.

- [ ] **Step 3: Implement**

In `js/widget-src/src/App.tsx`, modify the `Content` line:

```tsx
  // before:
  // const Content = TEMPLATES[initialOptions?.template ?? "card"] ?? SponsoredCard

  // Per-ad template (kin repo's LUL-64) wins when the current call's live
  // tool-result carries one; falls back to the registration-time default,
  // then to "card". A `??` chain alone is NOT sufficient here: it only
  // checks nullishness, not whether the name is actually a recognized key
  // in TEMPLATES, so an unrecognized-but-present live value would
  // incorrectly skip the registration-time fallback and fall straight to
  // "card". Both lookups must instead go through an own-property check
  // (`Object.prototype.hasOwnProperty`), not just presence/truthiness --
  // a bracket lookup for a prototype-chain name like "constructor" or
  // "toString" resolves through Object.prototype to a real, truthy value,
  // which would otherwise be misread as "recognized". This matters now
  // because the live value is admin-set, external data relayed from
  // `/slot` with no server-side allowlist -- unlike the registration-time
  // value, which `register_sponsored_widget()` validates before this code
  // ever runs. See
  // docs/superpowers/specs/2026-09-07-per-ad-template-live-override-design.md.
  const pick = (name?: string) =>
    name && Object.prototype.hasOwnProperty.call(TEMPLATES, name) ? TEMPLATES[name] : undefined
  const liveTemplate = state.kind === "loaded" ? state.template : undefined
  const Content = pick(liveTemplate) ?? pick(initialOptions?.template) ?? SponsoredCard
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npx vitest run src/App.test.tsx
```
Expected: all PASS, including every pre-existing test in `describe("App: template dispatch", ...)` (none of them set a live `template`, so they all still resolve from `initialOptions?.template` exactly as before)

- [ ] **Step 5: Run each changed package's full test suite once**

```bash
cd /Users/theking/Desktop/lulu-ads/.worktrees/lul-per-ad-template/python && .venv/bin/pytest -q
cd /Users/theking/Desktop/lulu-ads/.worktrees/lul-per-ad-template/js && npx vitest run
cd /Users/theking/Desktop/lulu-ads/.worktrees/lul-per-ad-template/js/widget-src && npx vitest run
```
Expected: all green, no regressions in any file this plan didn't touch

- [ ] **Step 6: Commit**

```bash
git add js/widget-src/src/App.tsx js/widget-src/src/App.test.tsx
git commit -m "feat(widget): live per-ad template overrides registration-time default"
```

---

### Task 6: Rebuild the widget bundle and bump versions

**Files:**
- Regenerate: `js/src/generatedWidgetBundle.ts` (via `js/widget-src`'s build)
- Regenerate: `python/lulu_ads/_generated_widget_bundle.py` (via `scripts/sync_widget_bundle.py`)
- Modify: `python/pyproject.toml:7` (`version`), `js/package.json:3` (`version`), `js/src/index.ts:41` (`SDK_VERSION` constant — this repo has a known, documented drift risk between this constant and `package.json`'s version; both must be bumped together)

**Interfaces:**
- Consumes: Tasks 1-5's source changes.
- Produces: the two published packages (`lulu-ads` on PyPI, `lulu-ads` on npm) at a new version, with a widget bundle that actually contains Tasks 3-5's compiled behavior.

- [ ] **Step 1: Build the widget bundle**

From `js/widget-src/`:
```bash
npm install
npm run build
```
This runs `tsc -b && vite build && node scripts/export-bundle.mjs`, which regenerates `js/src/generatedWidgetBundle.ts` from the compiled output.

- [ ] **Step 2: Sync the Python bundle from the TS one**

From the repo root:
```bash
scripts/sync-widget-bundle.sh
```
This regenerates `python/lulu_ads/_generated_widget_bundle.py` to be byte-identical to `js/src/generatedWidgetBundle.ts`.

- [ ] **Step 3: Verify both bundles actually changed**

```bash
git status --porcelain js/src/generatedWidgetBundle.ts python/lulu_ads/_generated_widget_bundle.py
```
Expected: both files show as modified (`M`). If either is unchanged, stop and investigate before proceeding — it means Task 5's `App.tsx` change didn't make it into the compiled output.

- [ ] **Step 4: Bump versions**

In `python/pyproject.toml`, change `version = "0.9.13"` to `version = "0.9.14"`.

In `js/package.json`, change `"version": "0.9.13"` to `"version": "0.9.14"`.

In `js/src/index.ts`, change `const SDK_VERSION = "0.9.13";` to `const SDK_VERSION = "0.9.14";`.

- [ ] **Step 5: Run the full test suite once more against the rebuilt bundle**

```bash
cd python && .venv/bin/pytest -q && cd ..
cd js && npx vitest run && cd ..
cd js/widget-src && npx vitest run && cd ../..
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add js/src/generatedWidgetBundle.ts python/lulu_ads/_generated_widget_bundle.py python/pyproject.toml js/package.json js/src/index.ts
git commit -m "chore: rebuild widget bundle, bump to 0.9.14"
```

---

### Task 7: Publish

**Files:** none (release step only)

- [ ] **Step 1: Publish the Python package**

From `python/`:
```bash
rm -rf dist/
python3 -m build
twine upload dist/*
```
(If `build`/`twine` aren't installed: `pip install build twine` first.)

- [ ] **Step 2: Publish the TypeScript package**

From `js/`:
```bash
npm publish
```
(`prepublishOnly` already runs `npm run build && cp ../README.md ./README.md` automatically.)

- [ ] **Step 3: Verify both registries show 0.9.14**

```bash
pip index versions lulu-ads 2>&1 | head -3
npm view lulu-ads version
```
Expected: `0.9.14` on both.

- [ ] **Step 4: Commit the version bump is already done (Task 6) — tag the release**

```bash
git tag v0.9.14
git push origin feat/per-ad-template-live-override --tags
```

(Merging this branch to `master`/opening a PR is a separate decision — see plan handoff. Don't push to `master` directly without checking with Tal, per this repo's own git-safety norms.)

---

## Self-Review Notes

- **Spec coverage:** all 5 code changes in the spec (client.py, index.ts, mcpBridge.ts, SponsoredCard.tsx, App.tsx) map to Tasks 1-5 exactly. Release steps (spec's "Release" section) map to Tasks 6-7.
- **Type consistency:** `template?: string` is spelled identically across `Sponsored` (Task 2), `RawSponsored`/`SponsoredData` (Task 3), `SponsoredCardState` (Task 4), and consumed as `state.template`/`initialOptions?.template` in `App.tsx` (Task 5) — verified no naming drift (e.g. no `templateName` vs `template` mismatch).
- **Out of scope, deliberately:** no changes to `register_sponsored_widget()`/`registerSponsoredWidget()`'s registration-time template validation (`TEMPLATES` tuple, `ValueError` on unknown value) — that's registration-time input validation, unrelated to this plan's live-override read path. No changes to `ads-server` or the `kin` repo. No changes to any first-party MCP server's pinned `lulu-ads` dependency version — that's a separate follow-up plan, gated on Task 7's publish actually landing (can't pin to a version that doesn't exist yet).
