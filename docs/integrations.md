# Framework integrations

Lulu Ads is a data source, not a middleware framework. Every adapter here does
the same three things: call `sponsored_slot`/`sponsoredSlot`, attach the
result under a `sponsored` key on the tool's own output, and fail open (any
ads failure — missing creds, network error, timeout, malformed response —
leaves the tool result exactly as the tool returned it). Nothing in this SDK
ever instructs a model to say, do, or render anything. The host decides.

All adapters resolve credentials the same way as the base client: explicit
args first, then `LULU_ADS_PUBLISHER_ID` / `LULU_ADS_API_KEY` /
`LULU_ADS_BASE_URL` env vars. Missing credentials never raise — the adapter
installs cleanly and every call becomes a no-op (`sponsored` stays absent).

stdio servers: every adapter on this page (`LuluAdsMiddleware`,
`withLuluAds`, the LangChain/CrewAI hooks) is already the endpoint-free,
data-only path — none of them need or accept a public `endpoint_url`, so
they all work unmodified on a stdio-transport server. Only the separate
`enable_lulu_ads`/`register_sponsored_widget` calls (the rendered MCP Apps
widget, not covered on this page) require one, and that piece genuinely
can't apply to stdio — see the main [README's "stdio servers"
section](../README.md#stdio-servers) for the full explanation.

## FastMCP (Python)

```python
from fastmcp import FastMCP
from lulu_ads.middleware import LuluAdsMiddleware

mcp = FastMCP("my-server")
mcp.add_middleware(LuluAdsMiddleware())
```

Requires `fastmcp>=3.0.0`. See `python/lulu_ads/middleware.py`.

## LangChain / LangGraph (Python)

```python
from langchain.agents import create_agent
from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

agent = create_agent(model, tools, middleware=[LuluAdsAgentMiddleware()])
```

Requires `langchain>=1.0`. `LuluAdsAgentMiddleware` subclasses
`langchain.agents.middleware.AgentMiddleware` and implements
`wrap_tool_call`/`awrap_tool_call`. When the wrapped `ToolMessage.content` is
JSON, `sponsored` is merged into the parsed payload and re-serialized; for
non-JSON content it lands in `additional_kwargs["sponsored"]` instead so the
message text itself is never rewritten. Pass `exclude_tools=(...)` to skip
specific tool names.

## CrewAI (Python)

```python
import lulu_ads.integrations.crewai as lulu_crewai

hook = lulu_crewai.install()  # call once, at process/crew startup
```

Requires `crewai>=1.9.1`. `install()` registers a global
`after_tool_call` hook via `crewai.hooks.register_after_tool_call_hook`. The
hook reads `context.tool_name`/`context.tool_result`, and — per CrewAI's
after-hook contract — returns either a replacement result string (JSON with
`sponsored` merged in, or the original text plus a disclosed one-line
suffix for non-JSON results) or `None` to leave the result untouched.
`install()` returns the hook function; pass it to
`crewai.hooks.unregister_after_tool_call_hook(hook)` to remove it (useful in
tests or when tearing down a crew).

## MCP servers (TypeScript)

```ts
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { LuluAds, withLuluAds } from "lulu-ads";

const server = new McpServer({ name: "my-server", version: "1.0.0" });
withLuluAds(server); // ads is optional — defaults to `new LuluAds({})` (env-driven)
```

The official TypeScript SDK has no server-side tool middleware hook
(`typescript-sdk#1238` is still open), so `withLuluAds` wraps
`McpServer.registerTool` itself: call it once, before registering any tools,
and every tool registered after that point gets a sponsored field attached to
its result. The field lands in two places — `structuredContent.sponsored`
(skipped if the tool declares an `outputSchema`, since an unlisted field would
fail validation) and the always-safe mirror
`_meta["ads.getlulu.dev/sponsored"]`. Pass `{ excludeTools: [...] }` to skip
specific tool names, or `{ timeoutMs }` to override the default cap (see
`js/src/index.ts` for the current adaptive default — it's changed more
than once as production evidence came in, so this doc intentionally
doesn't repeat a number that can go stale).

Requires `@modelcontextprotocol/sdk >= 1.x` (1.29.0 tested).

## Skybridge (TypeScript)

```ts
import { McpServer } from "skybridge/server";
import { withLuluAdsSkybridge } from "lulu-ads/skybridge";

const server = new McpServer({ name: "my-app", version: "1.0.0" });
withLuluAdsSkybridge(server); // call before registerTool, or any time before run()
```

Skybridge's `McpServer` is not a drop-in for the two adapters above: its
`registerTool` takes a 2-arg `(config, handler)` shape with `name` folded
into `config`, not the official SDK's 3-arg `(name, config, handler)` —
using `withLuluAds` on a Skybridge server would misread the config object as
the tool name. `withLuluAdsSkybridge` instead uses Skybridge's own protocol
middleware hook, `server.mcpMiddleware("tools/call", ...)` — an onion-model
hook built for exactly this, the same shape as FastMCP's `on_call_tool`.

Deliberately `_meta`-only: `mcpMiddleware` sees the call result but not the
tool's registered `outputSchema`, so `structuredContent` is never touched
(no way to confirm an unlisted `sponsored` field wouldn't fail validation).
The field always lands at `_meta["ads.getlulu.dev/sponsored"]`. Pass
`{ excludeTools: [...] }` to skip specific tool names, or `{ timeoutMs }` to
override the default cap.

Requires `skybridge >= 1.4.0`.

## Any agent runtime

The integrations above are conveniences over a runtime-agnostic contract.
Any loop that builds tool results — a Hermes-style agent pod, an OpenClaw
skill runner, a bespoke harness that isn't LangChain, CrewAI, MCP, or
Skybridge — can integrate directly:

1. After a tool call completes (and only on success — never on an error
   result), call `sponsored_slot(context)` (Python) or `sponsoredSlot({context})`
   (TypeScript) with an allowlisted context dict (`tool`, `category`, `query`,
   `route`, `locale`, `country` — no PII fields exist in the schema).
2. If the result is non-null, attach the labeled dict verbatim under a
   `"sponsored"` key on the tool result payload you're about to hand back to
   the model or the client.
3. If the result is `None`/`null` — inert client, backend down, timeout — do
   nothing. Never retry inline, never block the tool call waiting on ads.

Same three rules as every other adapter: **data, never a directive; never on
errors; allowlisted context only.**

This is also why there's no per-host adapter list here beyond the
frameworks above: the `sponsored` field is plain JSON on a standard MCP
tool result, so any MCP-speaking host — VS Code, Zed, Windsurf, Cline,
Goose, Grok, or anything else that calls your tools over the protocol —
already receives it once your server runs one of the adapters above, with
zero extra code and no host-specific integration. What differs host to
host is only whether it *renders* the field as a card (see
[Supported hosts](../README.md#supported-hosts) in the README for the
current, honestly-caveated picture) — the data itself is unconditional.

## OpenClaw / ClawHub skill authors

An AgentSkill's backing script (Python or Node) can call the SDK directly and
append the labeled sponsored object to the skill's own structured output —
there's no special Lulu Ads/OpenClaw glue required, just the same
`sponsored_slot`/`sponsoredSlot` call as any other runtime, documented above
under "Any agent runtime."

This is also why the object is intentionally boring: `{label: "Sponsored",
text, url}` with no rendering instructions, no markdown, no persuasive
copy generated by us. That's exactly the shape ClawHub's Skill Cards and
SkillSpector scanner want to see — a labeled data field with nothing hidden
in it passes review; a field that tries to talk the model into anything
would not.

## Why there is no LiteLLM adapter

LiteLLM's hooks (`pre_call`, `post_call_success`, etc.) operate on the model
request/response stream itself — they exist to let a proxy rewrite what the
model sees or says. Wiring sponsored content in at that layer would mean
injecting it into the model's input or output without the model (or, more to
the point, the end user reading the output) ever being able to tell it wasn't
part of the original response. That's undisclosed output tampering — the
exact failure mode this SDK's fail-open, label-always-"Sponsored",
data-not-directive design exists to prevent.

Tool-result decoration belongs in the tool layer, not the model layer — which
is what the FastMCP, LangChain, CrewAI, and MCP-TS adapters above all do.
LiteLLM-as-MCP-gateway (routing MCP tool calls through LiteLLM's proxy,
where our existing MCP-layer adapters would apply unchanged) remains a
partnership target — see the Task 22 brief — but there is no LiteLLM
request/response hook adapter in this SDK, and there will not be one.

## Runtime owners: response suffix

Everything above decorates a *tool result* — a data field a model may or may
not choose to surface. Runtimes that own the final response surface (a chat
bot, a WhatsApp/Telegram agent, a self-hosted assistant like OpenClaw, a
Hermes-style pod) have a second option: append a disclosed, human-readable
suffix to the message the user actually sees.

```python
from lulu_ads import LuluAds, format_suffix

sponsored = ads.sponsored_slot_sync(context={"tool": "search_flights"})
final_message = model_output + format_suffix(sponsored)
```

```ts
import { LuluAds, formatSuffix } from "lulu-ads";

const sponsored = await ads.sponsoredSlot({ context: { tool: "search_flights" } });
const finalMessage = modelOutput + formatSuffix(sponsored);
```

`format_suffix`/`formatSuffix` returns `"\n\n— Sponsored: {text} → {url}"`,
or `""` when there's nothing to show (`None`/`null`, or a malformed
sponsored object) — always safe to concatenate unconditionally.

This is deliberately **harness code, not a model instruction**: the suffix is
appended by your application after the model has already produced its final
output, with a plain string concatenation, not by asking the model to write
an ad. The model never sees the sponsored object, never decides whether to
include it, and never phrases it.

**If you don't own the render surface — you're a tool provider, not the
runtime showing the final message to the user — there is no suffix path.**
Ship the data field (via one of the adapters above, or the "Any agent
runtime" contract) and let the host decide whether and how to render it. Do
not attempt to smuggle a suffix into tool output text; that's a directive
wearing a data field's clothes, and it's exactly what this SDK is built to
avoid.

## Render kits: shipped vs. roadmap

The `sponsored` data field is intentionally render-agnostic — text, URL,
disclosure label, nothing else. Per-host native card affordances on top of
that same field raise render rates without changing the contract.

**Already shipped**, on top of the always-on data field: the MCP Apps
widget (`register_sponsored_widget`/`registerSponsoredWidget`,
`enable_lulu_ads`/`enableLuluAds` — see the README's
[Widget rendering](../README.md#widget-rendering-mcp-apps-ui) section) and
ChatGPT's `window.openai` bridge, both registered automatically by
`enable_lulu_ads`/`enableLuluAds`. See the README's
[Supported hosts](../README.md#supported-hosts) table for exactly which
hosts render either of these today.

**Still roadmap:** Gemini extension cards. Not shipped in this v0 — the
data field above is stable and forward-compatible with it; a render kit is
purely additive whenever it lands.
