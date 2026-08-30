# Supported surfaces — where Lulu Ads actually reaches today

"One SDK, every agent surface" is true, but not because this repo ships a
dozen framework-specific adapters. It's true because of how the SDK
attaches: at the **MCP server** (via `LuluAdsMiddleware`/`withLuluAds`,
[Quickstart](../README.md#quickstart)) or the raw
[`sponsored_slot`/`sponsoredSlot` contract](contract.md) directly. Once
`sponsored` is on a tool result, it travels with that result through
*whatever* calls the tool — the SDK doesn't need to know or care what's on
the other end. This page sorts every surface below into how it actually
gets there, using this repo's own bar: confirmed live > credible vendor
claim not independently reproduced > works via a generic mechanism, unverified
per-integration > not yet built. Never "should work."

## Direct adapters (dedicated code in this repo)

| Surface | Adapter | Docs |
|---|---|---|
| FastMCP (Python) | `LuluAdsMiddleware` / `enable_lulu_ads` | [→](integrations.md#fastmcp-python) |
| Official MCP SDK (TypeScript) | `withLuluAds` / `enableLuluAds` | [→](integrations.md#mcp-servers-typescript) |
| LangChain / LangGraph (Python) | `LuluAdsAgentMiddleware` | [→](integrations.md#langchain--langgraph-python) |
| CrewAI (Python) | `lulu_crewai.install()` | [→](integrations.md#crewai-python) |
| Skybridge (TypeScript) — the framework **Alpic** built and ships MCP/ChatGPT-App hosting around | `withLuluAdsSkybridge` | [→](integrations.md#skybridge-typescript) |

## Via MCP passthrough (no adapter needed — this is the actual mechanism, not a gap)

If your MCP server already has one of the two direct MCP adapters above
wired in, `sponsored` is just a field on that tool's result — any client
that calls the tool and passes through `structuredContent`/`_meta` sees it,
whether or not this repo has ever heard of that client. As of this SDK's
own 2026-08-30 survey of the agent-framework landscape, native MCP
tool-calling ships in:

- **Confirmed shipping MCP support** (per each project's own current
  docs/changelog, not independently re-tested by us the way the "Supported
  hosts" table's *rendering* claims are): LangGraph, Claude Agent SDK,
  OpenAI Agents SDK (first-class MCP support added in its April 2026
  overhaul), Mastra, Strands (AWS).
- **Likely, not checked in this pass**: Google ADK, Vercel AI SDK,
  Microsoft Agent Framework, LlamaIndex. These weren't in the specific
  "confirmed MCP support" list our survey turned up — treat as unverified
  until someone checks each one's current MCP client behavior directly,
  same standard as everything else in this repo.

None of the above need a Lulu Ads-specific integration to receive the data
field. What they will *not* get without one is the rendered MCP Apps
widget — that's still gated on the same `ui/initialize` handshake as
everywhere else (see the README's [Supported hosts](../README.md#supported-hosts)
table), and most of these are headless/backend frameworks with no chat
surface to render a widget into regardless.

## Chat hosts (rendering, not integration — see the main README)

ChatGPT, Claude (claude.ai), Claude Code, Cursor, VS Code/GitHub Copilot
Chat, Goose, Grok, Windsurf, Cline, Zed — this is what the README's own
[Supported hosts](../README.md#supported-hosts) table already tracks in
detail (tool-calling vs. rendered-widget status per host, each one cited).
Not repeated here to avoid two copies of the same claims drifting apart.

## Response-suffix runtimes (own the final message, not a tool result)

WhatsApp/Telegram/Slack/SMS bots, background agents, workflow runners —
anything that owns the literal text sent to a user rather than returning a
structured tool result. Covered generically by
[`format_suffix`](integrations.md#runtime-owners-response-suffix): append a
disclosed, human-readable line to your own output. This works for *any*
runtime in this category, including ones never named here — it's a
contract, not a per-platform integration, so there's nothing further to
verify per platform.

## AI app builders (Lovable, Bolt, Replit Agent, v0, Base44, Genspark, Manus, and similar)

Not evaluated yet. These platforms compile a spec/prompt into a deployed
app; whether the *apps they generate* can wire in an MCP server (and
therefore Lulu Ads) depends on each platform's own generated-code
capabilities, which we have not tested against any of them. Real,
verifiable companies (see this SDK's 2026-08-30 landscape survey), genuine
candidates — just not confirmed integration targets. Do not represent any
of these as a partner or a tested integration until one actually is.

## MCP hosting & registries

Smithery, Glama, the official MCP registry, mcp.so, Cloudflare (Workers-hosted
remote MCP servers), Alpic's own hosting product, and any self-hosted
custom server — Lulu Ads is server-side middleware, so it is fully
indifferent to where the server *runs* or is *listed*. Smithery and Glama
are also two of the marketplace's own ingestion sources (see
[getlulu.dev/mcps](https://getlulu.dev/mcps)); that's marketplace listing
coverage, a separate thing from SDK integration, and already real. No
hosting/registry platform needs anything from this SDK to "support" it —
that was already true for any custom MCP server on day one, and remains
true here.

## What "roadmap" actually means here

The only thing in this document that is genuinely unbuilt, not just
unverified, is the Gemini extension-card render kit (see the README's
[Render kits: shipped vs. roadmap](https://github.com/Lulu-The-Narwhal/lulu-ads#render-kits-shipped-vs-roadmap)).
Everything else above either already works today (direct adapter or MCP
passthrough) or is a real candidate nobody has evaluated yet — those are
different categories and this doc keeps them separate on purpose, the same
way the README's own hosts table never asserts "Live" on a "should work"
guess.
