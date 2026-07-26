<div align="center">

# lulu-ads

### *The monetization layer for the agent economy.*

**Monetize your MCP server or agent tool with one labeled sponsored line.**

[![PyPI](https://img.shields.io/pypi/v/lulu-ads.svg)](https://pypi.org/project/lulu-ads/)
[![npm](https://img.shields.io/npm/v/lulu-ads.svg)](https://www.npmjs.com/package/lulu-ads)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Backend](https://img.shields.io/badge/backend-live-brightgreen)](https://ads.getlulu.dev/health)
[![Publisher beta](https://img.shields.io/badge/publisher_beta-open-E07A00)](https://getlulu.dev/publishers)
[![Rev share](https://img.shields.io/badge/rev_share-70%25-blueviolet)](docs/contract.md)

[Quickstart](#quickstart) · [Integrations](#framework-integrations) · [Guarantees](#guarantees-enforced-in-code-not-just-promised) · [API contract](docs/contract.md) · [Hosted docs](https://getlulu.dev/docs) · [Blog](https://getlulu.dev/blog) · [Become a publisher](https://getlulu.dev/publishers)

<img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/lulu-ads-hero.jpg" alt="Lulu, the Lulu Ads narwhal mascot, celebrating on a Tel Aviv billboard — the agent economy has a monetization layer now" width="640" />

`70% to publishers · CPA only · 800ms fail-open · 0 prompt injections, by design`

</div>

Lulu Ads attaches a disclosed, labeled data field to your tool's own result.
The host model — Claude, Cursor, any agent — decides on its own judgment
whether it's relevant enough to surface. We never instruct it to.

<table>
<tr>
<th>What the SDK ships (a data field)</th>
<th>What the host renders (its choice)</th>
</tr>
<tr>
<td>

```json
{
  "sponsored": {
    "label": "Sponsored",
    "text": "Direct flights TLV–BKK from $412",
    "url": "https://ads.getlulu.dev/c/9f2a1c"
  }
}
```

</td>
<td>

> **Sponsored** — Direct flights TLV–BKK from $412
> [ads.getlulu.dev/c/9f2a1c](https://ads.getlulu.dev/c/9f2a1c)

</td>
</tr>
</table>

Zero-friction start — add the MCP server and let your agent do the rest:

```bash
claude mcp add --transport http lulu-ads https://ads.getlulu.dev/mcp
```

> monetize my server

It'll fetch the right integration guide for your stack, register a publisher
(with your consent), wire up the one-liner, and verify a slot went live.

**If it renders and gets clicked, you earn 70% on CPA. If it doesn't — nobody
pays, nothing breaks.**

**No prompt injection — we ship a data field; the host decides.**

## Quickstart

**Python**

```bash
pip install lulu-ads
# or: uv add lulu-ads
# or: poetry add lulu-ads
```

```python
from lulu_ads import LuluAds
ads = LuluAds(publisher_id="pub_123", api_key="lk_...")

result = search_flights("TLV", "BKK", dates)
result["sponsored"] = await ads.sponsored_slot(
    context={"tool": "search_flights", "category": "travel.flights"},
)
return result
```

FastMCP servers get it in one line — credentials come from the environment:

```bash
export LULU_ADS_PUBLISHER_ID=pub_123
export LULU_ADS_API_KEY=lk_...
```

```python
mcp.add_middleware(LuluAdsMiddleware())
```

**TypeScript**

```bash
npm install lulu-ads
# or: pnpm add lulu-ads
# or: yarn add lulu-ads
# or: bun add lulu-ads
```

```ts
import { LuluAds } from "lulu-ads";
const ads = new LuluAds({ publisherId: "pub_123", apiKey: "lk_..." });
result.sponsored = await ads.sponsoredSlot({ context: { tool: "search_flights" } });
```

No publisher ID yet? See [`docs/quickstart.md`](docs/quickstart.md) — three
ways to get one, none of them gated on the others.

**Tiered pricing (ads on a free tier, ad-free on paid)?** Pass `enabled` —
your own subscription check decides the value, no separate deployment or
scattered conditionals needed:

```python
result["sponsored"] = await ads.sponsored_slot(
    context={"tool": "search_flights"},
    enabled=user.tier != "paid",  # False resolves instantly, no network call
)
```

```ts
result.sponsored = await ads.sponsoredSlot({
  context: { tool: "search_flights" },
  enabled: user.tier !== "paid",
});
```

## Framework integrations

| Stack | One-liner | Docs |
|---|---|---|
| FastMCP (Python) | `mcp.add_middleware(LuluAdsMiddleware())` | [→](docs/integrations.md#fastmcp-python) |
| LangChain / LangGraph (Python) | `middleware=[LuluAdsAgentMiddleware()]` | [→](docs/integrations.md#langchain--langgraph-python) |
| CrewAI (Python) | `lulu_crewai.install()` | [→](docs/integrations.md#crewai-python) |
| MCP TS SDK | `withLuluAds(server)` | [→](docs/integrations.md#mcp-servers-typescript) |
| Runtime owners (chat bots, WhatsApp/Telegram agents) | `model_output + format_suffix(sponsored)` | [→](docs/integrations.md#runtime-owners-response-suffix) |
| Any other runtime / language | `sponsored_slot(context)` over the raw contract | [→](docs/integrations.md#any-agent-runtime) |

## Widget rendering (MCP Apps UI)

The plain `sponsored` field always ships and always works — some hosts
render it as a card purely on the model's own judgment, no instruction
anywhere. For hosts that support the [MCP Apps](https://github.com/modelcontextprotocol/ext-apps)
extension (`io.modelcontextprotocol/ui`), you can additionally register an
actual rendered widget instead of relying on that judgment call:

```python
from fastmcp import FastMCP
from lulu_ads.widget import register_sponsored_widget

mcp = FastMCP("my-server")
sponsored_app = register_sponsored_widget(
    mcp,
    endpoint_url="https://my-server.example.com/mcp",  # your public MCP connector URL
    text="Save 15% at checkout",
    url="https://example.com/deal",
    logo="https://example.com/logo.png",  # optional, see "Logos" below
)

@mcp.tool(app=sponsored_app)
def search(...): ...
```

Same helper, official TS SDK, for MCP servers built in Node instead of Python
(registration is `async` — it may fetch a logo before returning):

```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { registerSponsoredWidget } from "lulu-ads/widget";

const server = new McpServer({ name: "my-server", version: "1.0.0" });
const appMeta = await registerSponsoredWidget(server, {
  endpointUrl: "https://my-server.example.com/mcp", // your public MCP connector URL
  text: "Save 15% at checkout",
  url: "https://example.com/deal",
  logo: "https://example.com/logo.png", // optional, see "Logos" below
});

server.registerTool("search", { ...appMeta }, handler);
```

Ships a floating, rounded, gradient card (same visual system as
[getlulu.dev](https://getlulu.dev)) with a disclosed `Sponsored` label —
still just markup, never a directive. Three host-specific quirks this
handles for you: Claude requires an undocumented `_meta.ui.domain` value
derived from your endpoint URL (self-computed here, not a credential), the
widget must send a `ui/notifications/initialized` handshake on load or
Claude keeps the iframe hidden, and logos are inlined rather than linked
(next section) so the widget sandbox's own CSP can't silently drop them.
Verified live against production
(`dali.getlulu.dev/mcp`, [ext-apps#671](https://github.com/modelcontextprotocol/ext-apps/issues/671)),
current as of 2026-07-19 — Claude's own rendering of MCP Apps widgets was
broken platform-wide before that fix landed, so treat any "should render"
claim (including this one, elsewhere) as unverified until you've checked
it live in your own host.

The widget shows a shadcn `<Skeleton>` immediately on load, then swaps to
real content only once a live tool call arrives — `text`/`url`/`logo`
passed to `register_sponsored_widget()` are **not** rendered as initial
content; only `label`/`cta`/`accent*` from those options are actually used
by the live path (as defaults for fields the wire payload omits, and as
the static per-integrator brand theme). On every real tool call, the
widget listens for the MCP Apps host's own `ui/notifications/tool-result`
push (a fresh iframe is mounted per call, not reused — "per call, not per
tool" is a protocol guarantee, nothing had to be built server-side to get
it) and renders with *that call's* `structuredContent.sponsored` — live,
per-call ad content, not a fixed payload baked in once at registration. A
host that never sends the notification keeps showing the skeleton
indefinitely (not a fallback ad — see the open gap noted in
`js/widget-src/src/mcpBridge.ts`'s `InitialOptions` docstring); a call
with no `sponsored` field (the normal fail-open case) renders an empty
card with only the footer. Card, skeleton, and the "Powered by Lulu Ads"
footer are one compiled React/shadcn bundle shared byte-for-byte between
the Python and TypeScript SDKs (`js/widget-src/`, checked in, embedded by
both languages), and the footer always renders inside that same
persistent card shell, in every state.

### Logos

`logo` takes a URL to **fetch a brand mark from**, not a URL to embed
directly — pass it and the SDK downloads the image right there at
registration time and inlines it into the widget as a `data:` URI. This
isn't incidental: the MCP Apps spec has hosts enforce `img-src 'self' data:
<resourceDomains>` inside the widget's sandboxed iframe, and unless *you*
separately declare your logo's domain in that resource's CSP config, a
`<img src="https://your-cdn.com/logo.png">` gets silently dropped — no
error anywhere, the card just renders with a blank slot forever, in every
host. `data:` URIs are always allowed under that same rule, so fetching and
inlining server-side sidesteps the whole failure mode — there is no CSP
config for you to get right or forget.

A bad or unreachable `logo` never breaks registration — it's skipped (with
a warning log) and the card renders without one, same as leaving `logo`
unset. Only `image/png`, `image/jpeg`, `image/svg+xml`, `image/webp`, and
`image/gif` are accepted, capped at 200KB (the logo renders at 28×28 in the
card — there's no reason to ship more than that over the wire).

## CLI rendering

Terminals have no widget surface — the model's own text is the only
output there is, and it's genuinely the model's judgment call whether to
mention the disclosed line at all (never forced, ever — see Guarantees).
`LuluAdsMiddleware` / `withLuluAds` detect known CLI clients via the MCP
`clientInfo.name` sent at `initialize` (currently: `claude-code`, verified
live) and, when connected from one, append a bordered plain-text card to
`content[]` in addition to the plain field — still just data, still zero
instruction to the model, just formatted so it reads as a distinct block
instead of a plain sentence if the model does choose to relay it:

```
╭─ Sponsored ────────────────────────────────────╮
│ Search 700+ airlines in one place — Kiwi.com   │
│ finds routes other search engines miss.        │
╰─ via Lulu Ads ─────────────────────────────────╯
→ https://ads.getlulu.dev/c/9f2a1c
```

Known limitation, disclosed here rather than glossed over: some MCP
clients don't forward every `content[]` block to the model when
`structuredContent` is also present on the same result — an open
client-side bug in Claude Code, twice reported and twice closed without a
fix ([#55677](https://github.com/anthropics/claude-code/issues/55677) →
consolidated into
[#45575](https://github.com/anthropics/claude-code/issues/45575) →
auto-closed stale). Live-tested against Claude Code specifically
(2026-07-21): with `structuredContent` present (the shipped default), the
boxed card never reaches the model, but the plain `sponsored` field still
does — the model reliably surfaces it as an honest, labeled
"Sponsored: ..." line in its own words, 3/3 runs, no issues.

### `cliTextMode` — opt-in fix for the client bug above

We also tested the obvious-looking fix — omit `structuredContent` so
`content[]` has nothing competing with it — and the result depended
entirely on what else was in `content[]`:

- Ad **alone**, no real tool data alongside it: the card arrives every
  time, but the model flags it as a suspected prompt-injection attempt
  and warns the user off it, 3/3 runs. Worse than not showing it.
- Ad **alongside a real, complete rendering of the tool's own result**:
  the card arrives every time, the model treats it as an ordinary
  disclosed ad and mentions it neutrally, 3/3 runs. No suspicion.

So the fix is real, but conditional on your tool's own behavior — which
this SDK can't verify for you, hence opt-in, off by default:

```python
mcp.add_middleware(LuluAdsMiddleware(cli_text_mode=True))
```

```typescript
withLuluAds(server, ads, { cliTextMode: true });
```

Turn this on only if your tool's `content[]` already contains a
complete, human-readable rendering of the result on its own — not a
placeholder like "see structuredContent". When on, detected CLI clients
with no declared `outputSchema` get `structuredContent` stripped so
`content[]` (your tool's own text + our card) reliably reaches the
model. Tools that declare an `outputSchema` are never touched by this —
stripping `structuredContent` there would break client-side schema
validation outright (confirmed: `fastmcp.exceptions.ToolError`
"outputSchema defined but no structured output returned"), which is a
broken tool call, a strictly worse outcome than a dropped card. This SDK
never drops `structuredContent.sponsored` on schema'd tools to chase card
visibility, `cliTextMode` or not.

Until the upstream client bug is fixed, treat the CLI card as "renders
reliably once you opt in and your tool qualifies, on top of a disclosure
that already works either way" — same verify-in-your-own-host caveat as
the widget path above.

## Guarantees (enforced in code, not just promised)

| Guarantee | How |
|---|---|
| A tool call can never break because of ads | every failure path returns `None`/`null`; hard 800ms wall-clock timeout (3000ms when the call implies server-side classification) |
| Always disclosed | `label: "Sponsored"` is set by the SDK, never sourced from the response body |
| No prompt injection, ever | we ship a data field; there is no display instruction anywhere in the contract |
| No PII leaves your server | `context` is filtered against an allowlist client-side, before any request is built |
| Quality-gated | every creative passes [Dali](https://dali.getlulu.dev) scoring (≥70) before it can fill a slot |
| Intent, not identity | targeting uses this call's stated context only — no user profiles, no cross-session ID |
| Misconfigured? Still safe | missing credentials → client is inert, returns `None`/`null`, zero network calls |

## Why not just…

**…tell the model to mention a sponsor in its reply?**
Display instructions get MCP servers delisted by registries that scan for
injected directives. We ship a plain data object — `label`, `text`, `url` —
with no field, anywhere in the contract, that tells a model how to render or
phrase anything.

**…count impressions and charge per view?**
An "impression" only exists if a model actually rendered it, and that's
unverifiable from the server side — easy to game, hard to audit. We charge
CPA only, on a click that redeems a signed, server-verified token. Payment
maps to a real user action, not a claim.

**…scan the conversation to target better?**
Reading transcripts to target ads is a privacy trap: everything a user says
becomes ad-targeting data. We accept six allowlisted context keys — `tool`,
`category`, `query`, `route`, `locale`, `country` — stated intent for this
call only. No transcripts, no profiles, no PII fields exist in the schema.

## How it works

```
tool call
   │
   ▼
your tool's own result
   │
   ▼
POST /slot  (800ms cap — 3000ms when classifying a raw prompt — allowlisted context only)
   │
   ▼
labeled data field  { label: "Sponsored", text, url }   ← attached, never injected
   │
   ▼
host / model judgment   →   renders it, or doesn't — not our call
   │  user clicks
   ▼
GET /c/{token}   →   signed redirect, click recorded
   │
   ▼
advertiser's affiliate rails   →   POST /postback on conversion
   │
   ▼
70% publisher / 30% Lulu, on the ledger. Earnings accrue to your balance from the first audited conversion — cash out from $100.
```

Full wire-level detail: [`docs/contract.md`](docs/contract.md).

---

Docs: https://getlulu.dev/docs · [Quickstart](docs/quickstart.md) ·
[API contract](docs/contract.md) · [Integrations](docs/integrations.md) ·
[Publisher signup](https://getlulu.dev/publishers) · Quality gate:
[Dali](https://dali.getlulu.dev) · [MIT](LICENSE)

## Changelog

- **0.6.0** — The MCP Apps sponsored widget now shows **live, per-call ad
  content** instead of a fixed house ad baked in at registration time:
  rebuilt in React + shadcn/ui (`Card`, `Skeleton`, `Button`), compiled to
  a single self-contained bundle shared byte-for-byte by both SDKs
  (`js/widget-src/`). The widget shows a skeleton immediately on load,
  then listens for the MCP Apps host's own `ui/notifications/tool-result`
  push — which the spec already delivers once per call, to a fresh iframe
  per call, with no server-side change needed — and swaps to that call's
  real `structuredContent.sponsored` data. The `text`/`url`/`logo` passed
  to `register_sponsored_widget()`/`registerSponsoredWidget()` are now
  just the starting/fallback content for hosts that never push the live
  update. The "Powered by Lulu Ads" footer renders once, immediately, and
  is never itself part of the skeleton→card swap. Live-verified against a
  real host (claude.ai) with a throwaway test server: skeleton renders
  before the tool call resolves, swaps to the real per-call card once it
  does, the footer never disappears or reflows during the swap, and two
  tool calls in the same turn render two fully independent widget
  instances, each showing only its own call's data — confirming the "per
  call, not per tool" behavior this feature is built on. (The CTA's
  `ui/open-link` redirect — vs. a raw navigation — was re-confirmed by
  static code inspection and this repo's existing unit tests during this
  same pass; live click-through capture was attempted but blocked by
  browser-automation tooling limits reaching inside the host's
  double-sandboxed iframe, not by any observed product failure.)
- **0.4.0** — Automatic pre-connect on construction for LangChain's
  `LuluAdsAgentMiddleware`, CrewAI's `install()`, and TypeScript's
  `withLuluAds` (matching the FastMCP `LuluAdsMiddleware`, which already
  had this). Also: FastMCP's `LuluAdsMiddleware` and LangChain's
  `LuluAdsAgentMiddleware` now additionally warm the **async** connection
  pool their `await`ed `sponsored_slot()` traffic actually uses — the
  construction-time warm-up above only ever touched the sync client, a
  separate pool the async path never touches. `LuluAds.async_warm_up()`
  is fired once per instance from a real framework lifecycle hook on the
  live serving event loop (FastMCP's `on_initialize`, LangChain's
  `abefore_agent`), since a background thread can't safely pre-warm a
  connection meant for a different event loop. Gated by the same
  `auto_warm_up` flag as the sync warm-up (this async path is Python-only —
  TypeScript's `autoWarmUp` only ever had one pool to gate). This is the fix
  that closes the cold-start gap for `dali-mcp` in production, which
  consumes the async path. Short-TTL (default 45s) success-only cache in
  both base clients, keyed on resolved category or a hash of the prompt
  text. Corrected documentation: the real default timeout is 800ms (fast
  path) / 3000ms (classify path) adaptive, not a flat 300ms.
- **0.3.7** — `cliTextMode` (opt-in, off by default): fixes the Claude Code
  content[]-drop bug for real, but only for tools whose `content[]` already
  stands on its own without `structuredContent` — live-tested both
  qualifying and non-qualifying cases, see "CLI rendering". Never touches
  tools with a declared `outputSchema` (would break client-side schema
  validation, confirmed via `fastmcp.exceptions.ToolError`).
- **0.3.6** — automatic connection warm-up on `LuluAdsMiddleware` construction
  (`auto_warm_up`, on by default): a genuinely cold first tool call measured
  804ms against the 800ms fast-path default — right at the ceiling, not
  under it. `LuluAds` itself still never auto-warms (a network call as a
  constructor side effect is surprising in a general-purpose client), but
  the middleware is the "one line, zero config" promise, so it warms itself.
- **0.3.5** — fixed a hardcoded 300ms default `timeout_ms` on
  `LuluAdsMiddleware` that silently dropped real, fillable ads on real
  network latency — every test in the suite used an instant mock transport,
  which is exactly why this shipped unnoticed. Default is now `None`,
  deferring to `LuluAds`'s own conditional 800ms/3000ms default.
- **0.3.4** — CLI card gets rounded corners and a "via Lulu Ads" footer
  (Unicode box-drawing only — a live test against Claude Code confirmed it
  strips raw ANSI color escapes from tool output before the model sees
  them, so color was never on the table). Also live-tested and explicitly
  rejected dropping `structuredContent` to force `content[]` through: it
  does make the card arrive, but the model then flags it as suspected
  prompt injection and warns the user off it — worse than the status quo,
  where the plain field still gets surfaced honestly even without the
  card. See "CLI rendering" for the full writeup.
- **0.3.3** — CLI-adaptive rendering: `LuluAdsMiddleware` / `withLuluAds` detect
  known CLI clients via the MCP `clientInfo.name` sent at `initialize`
  (currently: `claude-code`, verified live) and append a bordered plain-text
  card to `content[]` for them, in addition to the plain field — terminals
  have no widget surface, so this is the CLI-safe equivalent of the MCP Apps
  widget above. Still just data; see "CLI rendering" for the disclosed known
  limitation on some clients' `content[]` forwarding.
- **0.3.0** — `register_sponsored_widget()` / `registerSponsoredWidget()` gain
  a `logo` option: fetched server-side at registration time and inlined into
  the widget as a `data:` URI, so it renders under the widget sandbox's CSP
  (`img-src 'self' data: <resourceDomains>`) with no `resourceDomains` config
  needed on your part — a raw remote logo URL would otherwise be silently
  dropped, with no error anywhere. A bad/unreachable logo never breaks
  registration; the card just renders without one. TypeScript's
  `registerSponsoredWidget()` is now `async` (it may need to fetch the logo
  before returning) — add `await` at existing call sites.
- **0.2.0** — `register_sponsored_widget()` (Python: `lulu_ads.widget`, now also
  TypeScript: `lulu-ads/widget`, official MCP SDK): registers a real rendered
  MCP Apps UI sponsored card on your server (not just the plain JSON field),
  handling Claude's undocumented iframe-domain requirement and the
  `ui/notifications/initialized` handshake for you. Generalizes the fix
  verified live on `dali.getlulu.dev/mcp` against
  [ext-apps#671](https://github.com/modelcontextprotocol/ext-apps/issues/671).
  Both SDKs produce byte-identical `_meta.ui.domain` values for the same
  endpoint URL.
- **0.1.1** — persistent HTTP clients in the Python SDK (per-call client
  construction could burn the entire slot budget on CPU-constrained
  containers; clients are now created once per `LuluAds` instance and reused
  with keep-alive). Fail-open behavior unchanged.
- **0.1.0** — initial release: Python + TypeScript clients, FastMCP /
  LangChain / LangGraph / CrewAI / MCP-TS adapters, suffix helpers, MCP
  concierge onboarding.
