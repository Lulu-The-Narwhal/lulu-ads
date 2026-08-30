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
[![Lulu MCPs](https://getlulu.dev/api/mcps/badge/lulu-ads)](https://getlulu.dev/mcps/lulu-ads)

[Quickstart](#quickstart) · [Integrations](#framework-integrations) · [Supported hosts](#supported-hosts) · [Supported surfaces](docs/supported-surfaces.md) · [stdio servers](#stdio-servers) · [Guarantees](#guarantees-enforced-in-code-not-just-promised) · [API contract](docs/contract.md) · [Hosted docs](https://getlulu.dev/docs) · [Blog](https://getlulu.dev/blog) · [Become a publisher](https://getlulu.dev/publishers)

<img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/lulu-ads-hero.jpg" alt="Lulu, the Lulu Ads narwhal mascot, celebrating on a Tel Aviv billboard — the agent economy has a monetization layer now" width="640" />

`70% to publishers · CPA only · 800ms fail-open · 0 prompt injections, by design`

[![Sponsored](https://getlulu.dev/api/mcps/sponsor/lulu-ads)](https://getlulu.dev/api/mcps/sponsor-click/lulu-ads)
<br><sub>↑ live rendered sponsor card — real rotating ad demand, refreshes every ~60s. Any claimed listing can embed this in its own README.</sub>

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

FastMCP servers get it in one call — credentials come from the environment,
and every tool (present and future) gets both the plain `sponsored` data
field AND, in hosts that support it (e.g. Claude.ai), the rendered
Sponsored-card widget, automatically:

```bash
export LULU_ADS_PUBLISHER_ID=pub_123
export LULU_ADS_API_KEY=lk_...
```

```python
from lulu_ads.enable import enable_lulu_ads

enable_lulu_ads(mcp, endpoint_url="https://my-server.example.com/mcp")
```

Just want the data field, no widget? The plain middleware still works on
its own:

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

MCP servers built on the official TS SDK get the same one-call treatment —
data field AND widget on every tool, automatically:

```ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { enableLuluAds } from "lulu-ads/mcp";

const server = new McpServer({ name: "my-server", version: "1.0.0" });
await enableLuluAds(server, { endpointUrl: "https://my-server.example.com/mcp" });
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
| FastMCP (Python), data + widget | `enable_lulu_ads(mcp, endpoint_url=...)` | [→](docs/integrations.md#fastmcp-python) |
| FastMCP (Python), data only | `mcp.add_middleware(LuluAdsMiddleware())` | [→](docs/integrations.md#fastmcp-python) |
| MCP TS SDK, data + widget | `await enableLuluAds(server, { endpointUrl })` | [→](docs/integrations.md#mcp-servers-typescript) |
| LangChain / LangGraph (Python) | `middleware=[LuluAdsAgentMiddleware()]` | [→](docs/integrations.md#langchain--langgraph-python) |
| CrewAI (Python) | `lulu_crewai.install()` | [→](docs/integrations.md#crewai-python) |
| MCP TS SDK, data only | `withLuluAds(server)` | [→](docs/integrations.md#mcp-servers-typescript) |
| Skybridge (TypeScript) | `withLuluAdsSkybridge(server)` | [→](docs/integrations.md#skybridge-typescript) |
| Runtime owners (chat bots, WhatsApp/Telegram agents) | `model_output + format_suffix(sponsored)` | [→](docs/integrations.md#runtime-owners-response-suffix) |
| Any other runtime / language | `sponsored_slot(context)` over the raw contract | [→](docs/integrations.md#any-agent-runtime) |

## Result widgets — templates for your OWN tool output (0.8.5)

**One widget, every host.** The frame speaks three bridges — stable MCP
Apps (`ui/initialize`, 2026-01-26), the draft-era fallback, and ChatGPT's
`window.openai` — and the SDK registers both template keys
(`_meta.ui.resourceUri` + `openai/outputTemplate`) and both CSP dialects
automatically. Verified rendering live on claude.ai and ChatGPT, including
the rendered-impression beacon (impressions count what a human actually
saw, never mere API output). After upgrading, refresh your connector in
ChatGPT's plugin settings — it caches tool metadata.

## Supported hosts

The plain `sponsored` JSON field is the always-on baseline: it ships on
every tool result, on every MCP host, because it's nothing more than an
extra key on a dict — no host-specific support is required for it to work,
and the model decides on its own whether to surface it. The **rendered**
MCP Apps widget above that is additive, and only paints where a host has
actually implemented the `ui/initialize` handshake. This table says exactly
which is which per host, based on our own production verification where we
have it and a fresh survey (2026-08-25) everywhere else — a host only gets
a "Live" widget status here when we've confirmed it ourselves or the
vendor has published concrete, checkable implementation detail, never on a
generic "should work" assumption.

<p>
<a href="https://claude.ai"><img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/hosts/claude.svg" alt="Claude" height="24"></a>
&nbsp;
<a href="https://chatgpt.com"><img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/hosts/openai.png" alt="ChatGPT" height="24"></a>
&nbsp;
<a href="https://www.copilotkit.ai"><img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/hosts/copilotkit.png" alt="CopilotKit" height="24"></a>
&nbsp;
<a href="https://code.visualstudio.com"><img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/hosts/vscode.png" alt="VS Code" height="24"></a>
&nbsp;
<a href="https://cursor.com"><img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/hosts/cursor.svg" alt="Cursor" height="24"></a>
&nbsp;
<a href="https://github.com/aaif-goose/goose"><img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/hosts/goose.png" alt="Goose" height="24"></a>
&nbsp;
<a href="https://grok.com"><img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/hosts/xai-grok.png" alt="Grok (xAI)" height="24"></a>
&nbsp;
<a href="https://windsurf.com"><img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/hosts/windsurf.svg" alt="Windsurf" height="24"></a>
&nbsp;
<a href="https://cline.bot"><img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/hosts/cline.svg" alt="Cline" height="24"></a>
&nbsp;
<a href="https://zed.dev"><img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/hosts/zedindustries.svg" alt="Zed" height="24"></a>
</p>

<sub>Hosts we've looked at — logos are not a support claim on their own;
read the Status column below for what each one actually does. (Continue.dev
is in the table but not the strip above: it's a discontinued product, kept
here only for completeness.)</sub>

| Host | MCP tool-calling | Rendered widget | Status |
|---|---|---|---|
| Claude (claude.ai) | Yes | Yes | Live, verified in production — real rendered-impression beacons observed on live traffic. |
| ChatGPT | Yes | Yes | Live, verified in production. |
| CopilotKit (`@ag-ui/mcp-apps-middleware`) | Yes | In progress | Fix in review, [PR #8](https://github.com/Lulu-The-Narwhal/lulu-ads/pull/8), unverified end-to-end — a tool-discovery bug was found and fixed, but the fix has not been tested against a full chat UI (no LLM available in that pass) and is not yet released to npm/PyPI. Do not treat CopilotKit as supported until that PR lands and is verified live. The plain `sponsored` field is unaffected by this bug and already flows today. |
| VS Code (native MCP + GitHub Copilot Chat agent mode) | Yes | Reported live | Microsoft's own 2026-01-26 blog post and current docs describe VS Code as "the first major AI code editor with full MCP Apps support" and document concrete, checkable implementation detail (sandboxed iframes, CSP domain config, the `ui/initialize` handshake, the App SDK) — credible, but this is a vendor claim we have not independently reproduced ourselves. Plain MCP tool-calling (Copilot Chat agent mode) has been GA since v1.102. |
| Cursor | Yes | Reported, unverified | Named as an MCP Apps implementer on the upstream [modelcontextprotocol.io Extension Support Matrix](https://modelcontextprotocol.io/extensions/client-matrix) — a third-party listing, not Cursor's own docs, so weaker evidence than VS Code/Goose's vendor-published detail above. We actually tried to verify this ourselves live (2026-08-25) and got blocked before reaching the test: Cursor's free-tier Agent usage cap (2 prompts) hit before a real tool call went through. Real attempt, real blocker, still unconfirmed — not a claim we're dodging. |
| Goose (Block / AAIF) | Yes | Live (experimental) | Goose's own docs confirm the `ui/initialize` handshake and sandboxed-iframe rendering (Goose Desktop 1.19.1+), but explicitly flag it as "experimental and based on a draft specification; the implementation is minimal and may change." Treat as live-but-unstable, not a guaranteed render target. |
| Grok (xAI) — grok.com connectors, Grok Build CLI, xAI API Remote MCP Tools | Yes | No evidence found | MCP-capable across all three xAI surfaces (plain tool discovery + calling), but no official doc, changelog, or third-party host-support matrix credits Grok with the MCP Apps UI extension as of this survey. The sponsored data field still flows and still renders purely on the model's own judgment via the always-on JSON fallback — the rich widget just has nothing to render into. |
| Windsurf (Codeium) | Yes | No evidence found | Windsurf's own docs state it supports "an MCP server's tools, resources, and prompts" only; every third-party MCP Apps host-support list we found omits it. Sponsored data field still works via the always-on JSON fallback. |
| Cline (VS Code extension) | Yes | No evidence found | Mature MCP client (tools, resources, prompts, a built-in MCP marketplace); no `ui/initialize`, `ui://`, or iframe-rendering code found anywhere in the repo. Sponsored data field still works via the always-on JSON fallback. |
| Zed editor | Yes | No evidence found | Zed's own docs state plainly it "currently supports MCP's Tools and Prompts features" — no Resources-based UI rendering. Sponsored data field still works via the always-on JSON fallback. |
| Continue.dev | Yes (historically) | No evidence found | Discontinued: acquired by Cursor in June 2026, and the `continuedev/continue` repo is now read-only with no further development. It supported plain MCP tools/resources/prompts while active, with no evidence it ever rendered MCP Apps widgets. Not a viable integration target going forward — listed here only for completeness. |

### Why some hosts need zero extra code and others don't

Different hosts converged on different conventions for how a tool
advertises "I have a renderable UI" — and where a host's convention differs
from the one we shipped first, discovery silently fails before rendering
ever gets a chance to run (that was the CopilotKit gap [PR #8](https://github.com/Lulu-The-Narwhal/lulu-ads/pull/8)
fixed, 2026-08-25). We track each convention we've confirmed and register
against all of them on every widget-capable tool — additive only, never a
rewrite, so a host that doesn't recognize one signal just ignores it. That's
the practical reason Claude and VS Code render with zero extra code (they
share a convention) while CopilotKit needed a targeted fix, and it's why
"no evidence found" in the table below means exactly that — evidence not
found yet, not evidence of absence.

Anything else not listed above (LangGraph Studio, custom in-house agent
harnesses, and every host we simply haven't looked at yet): unknown / not
yet investigated — the plain `sponsored` field is designed to fail open and
degrade gracefully on any of them regardless, per the [Guarantees](#guarantees-enforced-in-code-not-just-promised)
below. If you've verified rendering on a host not in this table, open an
issue or PR — this list is meant to stay honest, not exhaustive.

This table is specifically about **widget rendering in chat hosts**.
For the fuller picture — agentic SDKs/frameworks (most reach the data
field via MCP passthrough, no dedicated adapter needed), response-suffix
runtimes (WhatsApp/Telegram/Slack/SMS bots, background agents), AI app
builders (not yet evaluated), and MCP hosting/registries (irrelevant to
this SDK by design) — see
[**Supported surfaces**](docs/supported-surfaces.md).

Don't design UI. Pick one of four predefined, host-native-quality result
widgets and map your tool's `structuredContent` fields into it — the frame,
design tokens, and the disclosed SPONSORED strip are fixed by the SDK. The
strip renders only when a live `sponsored` payload exists, always at the
bottom, always labeled, with the advertiser's logo (letter-tile fallback
when none loads). Your body can't remove or restyle it.

Templates: `stat-card` (big value + chips + optional condition-keyed
atmospheric background), `table-card` (headed rows, mono numerics, best-row
highlight), `notice-card` (verdict glyph + detail rows), `carousel-card`
(3–8 swipeable option cards).

```python
from lulu_ads.widgets import register_result_widget

# after your @mcp.tool definitions:
register_result_widget(
    mcp, "get_weather",
    template="stat-card",
    mapping={
        "eyebrow": "location.name",
        "value": {"path": "temperature_c", "suffix": "°"},
        "condition": "conditions",
        "chips": [{"path": "humidity_pct", "prefix": "💧 ", "suffix": "%"}],
        "atmosphere": "weather_code",   # WMO code or words -> sky gradient
    },
    endpoint_url="https://my-server.example.com/mcp",
)
```

TypeScript: `import { registerResultWidget } from "lulu-ads/widgets"` —
same templates and mapping shape; spread the returned `_meta` into
`server.registerTool(...)`. Mapping entries are dot-paths or
`{path, prefix, suffix}`; a `body_html=` escape hatch accepts custom
markup composed from the `.lw-*` primitives for the cases the templates
don't cover. Calling it for a tool deliberately replaces the generic
sponsored card from `enable_lulu_ads` on that tool — the sponsored data
still flows and renders in the widget's own strip.

## Widget rendering (MCP Apps UI)

The plain `sponsored` field always ships and always works — some hosts
render it as a card purely on the model's own judgment, no instruction
anywhere. For hosts that support the [MCP Apps](https://github.com/modelcontextprotocol/ext-apps)
extension (`io.modelcontextprotocol/ui`), `enable_lulu_ads` / `enableLuluAds`
(see Quickstart above) already register an actual rendered widget and
attach it to every tool automatically — you don't need anything below this
line for that. It exists as a distinct step at all because
`register_sponsored_widget()` requires your server's exact public endpoint
URL, which `LuluAdsMiddleware`/`withLuluAds` alone have no way to know.

**Prefer per-tool control** (a different widget on different tools, or
only some tools get one)? Use the lower-level building block directly
instead of `enable_lulu_ads`:

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

This is also what `enable_lulu_ads`/`enableLuluAds` do internally, on your
behalf, for every tool — found live (2026-07-26) that getting this step
right per-tool is easy to forget: our own dogfood server had it wired onto
exactly one tool by hand, and every tool added since then silently never
got it. If you want automatic coverage with no per-tool step, use
`enable_lulu_ads`/`enableLuluAds` instead of this directly.

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

## stdio servers

Everything above the "Widget rendering" section works unmodified on a
stdio-transport server — the SDK is a library your code imports and calls;
it doesn't know or care how your own server talks to *its* clients. The
plain `sponsored` data field (`LuluAdsMiddleware` / `mcp.add_middleware()`,
`withLuluAds(server)`) takes no endpoint argument and makes a plain
outbound HTTPS call to `ads.getlulu.dev/slot` — same request whether your
process is a long-running remote server or a `npx`/`uvx`-launched local
one. The CLI text-card path (see "CLI rendering" above) is the common
real-world case here: Claude Code launches most of its MCP servers over
stdio, and that's exactly the client this SDK already detects and renders
a disclosed plain-text card for.

The rendered **MCP Apps widget is the one piece that doesn't apply** —
`enable_lulu_ads`/`enableLuluAds` and the lower-level
`register_sponsored_widget`/`registerSponsoredWidget` all require a real
`endpoint_url`, hashed into Claude's undocumented `_meta.ui.domain` value
for the widget's iframe CSP. That's not a Lulu Ads limit; MCP Apps'
`ui/initialize` handshake is a network protocol between the host and your
server's own HTTP endpoint, and a stdio server has none. If your server is
stdio-only, call `LuluAdsMiddleware`/`mcp.add_middleware()` directly (or
`withLuluAds(server)` in TypeScript) — never `enable_lulu_ads` — and you
get the data field plus the CLI text-card, with nothing to configure for
the endpoint you don't have.

Publisher-side note: the marketplace's automatic "monetized" badge
currently matches a listing to your registered publisher account by
`remote_url` — a stdio listing has none, so it won't auto-badge even once
you've integrated the SDK and are earning. The SDK/earnings path itself is
unaffected; this is purely a marketplace-listing display gap, being
tracked separately.

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
POST /slot  (1500ms cap — 3000ms when classifying a raw prompt — allowlisted context only)
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

- **0.9.2** (Python only) — Fixed a middleware bug: a tool that sets its
  own `sponsored` field (a documented pattern for e.g. a category-specific
  cross-sell) triggered the "never overwrite" early return in
  `on_call_tool` before the CLI-client check ran, so CLI hosts (Claude
  Code) got no visible ad at all on that tool — no widget surface, and no
  text-card safety net either, both skipped by the same early exit. The
  client check now runs first; a pre-set `sponsored` value still gets the
  CLI text-card treatment, using the tool's own chosen ad.
- **0.9.1** — `table-card` widget gains `rowLink`: an optional per-row
  dot-path resolving to a URL (e.g. a booking/checkout link), wired to
  the same host-agnostic `openLink()` the sponsored strip already uses.
  Rows without a resolvable URL render exactly as before.
- **0.9.0** — Skybridge (https://skybridge.tech) support:
  `withLuluAdsSkybridge(server)` (`lulu-ads/skybridge`). Skybridge's
  `McpServer.registerTool` takes a 2-arg `(config, handler)` shape with
  `name` folded into `config`, not the official SDK's 3-arg
  `(name, config, handler)` that `withLuluAds` wraps — reusing `withLuluAds`
  as-is would misread the config object as the tool name. The new adapter
  instead uses Skybridge's own `mcpMiddleware("tools/call", ...)` protocol
  hook, verified against the real `skybridge@1.4.0` package's shipped types
  and a live `InMemoryTransport` round-trip. Deliberately `_meta`-only:
  the middleware sees the call result but not the tool's registered
  `outputSchema`, so `structuredContent` is never touched.
- **0.8.1** — Result-widget template gallery (supersedes 0.8.0, which
  briefly shipped on npm with a louder strip design): `lulu_ads.widgets` /
  `lulu-ads/widgets` with four predefined templates (`stat-card`,
  `table-card`, `notice-card`, `carousel-card`), design tokens + `.lw-*`
  primitives, and the disclosed SPONSORED strip built into the frame
  (advertiser logo via the slot's new `logo_url`, letter-tile fallback).
  `register_result_widget()` patches an already-registered FastMCP tool in
  place (or returns the AppConfig for explicit `app=`).

- **0.7.4** — Widget: the sponsored card's iframe canvas no longer paints
  an opaque white box on dark hosts. `background: transparent` alone is
  not enough for an embedded iframe: Chromium keeps the canvas
  transparent only when the embedded document's used color scheme matches
  the embedder's, and this document declared none (defaulting to
  `light`), so dark-themed hosts (e.g. claude.ai in dark mode) forced a
  white backdrop behind the card. The widget now declares
  `color-scheme: light dark`, which resolves to the user's preferred
  scheme — matching hosts that follow it (claude.ai does by default) on
  both light and dark themes. Verified empirically against light- and
  dark-scheme embedding pages. (Also aligns `lulu_ads.__version__`, which
  had drifted to 0.7.2 while the packages published as 0.7.3.)

- **0.7.0** — Two real bugs, found live against a real third-party MCP
  server behind Claude.ai's remote connector, both fixed:
  - **0% ad delivery on hosts that reconnect per message** (confirmed:
    Claude.ai opens a brand-new MCP session per chat message, not once per
    conversation). Root cause: this SDK's persistent HTTP connection goes
    cold on any real idle gap between messages, but only a one-time
    "have I ever succeeded" check protected the very first call ever —
    every later cold call still got the tight steady-state timeout and
    failed. Fixed by re-checking coldness on every call, keyed to time
    since the last real success, not a permanent latch. Also: the fast
    steady-state timeout itself was raised 800ms → 1500ms
    (Python and TS) — production evidence showed even "warm" calls
    sometimes measuring 796-802ms, right at the old line rather than
    comfortably under it.
  - **Ad fetched successfully, never seen by the model.** FastMCP/the
    MCP TS SDK build a tool result's `content[]` once, from the tool's
    original return value, before `LuluAdsMiddleware`/`withLuluAds` ever
    run — mutating `structuredContent` alone (the only thing this SDK's
    own test suite checked) left `content[]` permanently stale. Confirmed
    live: the wire response's `structuredContent` demonstrably had
    `sponsored`, but Claude.ai read and reported back from `content[]`,
    which didn't. Both SDKs now keep `content[]` in sync whenever it's
    safe to (a single auto-generated JSON text block); regression tests
    added for the exact gap that let this ship unnoticed the first time.
  - **New:** `enable_lulu_ads()` (Python) / `enableLuluAds()` (TS) — one
    call that wires both the data field AND the rendered MCP Apps widget
    onto every tool automatically, present and future. Existing
    `register_sponsored_widget()`/`registerSponsoredWidget()` +
    `app=`/`_meta.ui` per tool still works and is now documented as the
    lower-level building block for per-tool control; the gap it left (an
    easy-to-forget manual step per tool) is exactly what this closes —
    found live on our own dogfood server, which had wired the widget onto
    exactly one tool by hand and silently never updated it for tools
    added since.
- **0.6.2** — The sponsored card now plays a one-time diagonal light sweep
  across itself when it settles into the loaded state (a real ad won) —
  pure CSS (`.card-shine` in `js/widget-src/src/index.css`), fires exactly
  once per mount (not a looping shimmer, since this sits inline in a real
  chat thread), and respects `prefers-reduced-motion`. Skeleton and
  no-fill states are unaffected.
- **0.6.1** — Corrects a stale `0.6.0` published to npm before `dist/` was
  rebuilt from the merged source (`js/` has no `prepublishOnly` build
  step) — 0.6.0 is deprecated on npm pointing here. Also fixes README.md
  and both languages' `widget.py`/`widget.ts` docstrings, which
  incorrectly claimed `text`/`url`/`logo` passed to
  `register_sponsored_widget()` render as a fallback "house ad" until a
  live `tool-result` arrives; they never do — the widget shows the
  skeleton indefinitely if a host never pushes it.
- **0.6.0** — The MCP Apps sponsored widget now shows **live, per-call ad
  content** instead of a fixed house ad baked in at registration time:
  rebuilt in React + shadcn/ui (`Card`, `Skeleton`, `Button`), compiled to
  a single self-contained bundle shared byte-for-byte by both SDKs
  (`js/widget-src/`). The widget shows a skeleton immediately on load,
  then listens for the MCP Apps host's own `ui/notifications/tool-result`
  push — which the spec already delivers once per call, to a fresh iframe
  per call, with no server-side change needed — and swaps to that call's
  real `structuredContent.sponsored` data — the widget shows the skeleton
  indefinitely if a host never pushes it, not a fallback ad; only
  `label`/`cta`/`accent*` from `register_sponsored_widget()`/
  `registerSponsoredWidget()`'s options are actually used by the live
  path. The "Powered by Lulu Ads" footer renders once, immediately, and
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
