# lulu-ads

**Monetize your MCP server or agent tool with one labeled sponsored line.**

Lulu Ads attaches a disclosed, labeled data field to your tool responses.
The host model (Claude, Cursor, any agent) decides on its own judgment
whether it's relevant enough to surface — we never instruct a model to
display anything. If it renders and gets clicked, you earn 70% on CPA.
If it doesn't — nobody pays, nothing breaks.

## Zero-friction start (MCP)

Add the Lulu Ads MCP server and ask your agent to do the rest:

```bash
claude mcp add --transport http lulu-ads https://ads.getlulu.dev/mcp
```

Then just say:

> monetize my server

The agent will fetch the right integration guide for your stack, register a
publisher (with your consent), wire up the one-liner below, and verify it
produced a live slot.

## Quickstart (Python)

```bash
pip install lulu-ads
```

```python
# pip install lulu-ads
from lulu_ads import LuluAds
ads = LuluAds(publisher_id="pub_123", api_key="lk_...")

result = search_flights("TLV", "BKK", dates)
result["sponsored"] = await ads.sponsored_slot(
    context={"tool": "search_flights", "category": "travel.flights"},
    timeout_ms=150,
)
return result
```

One line for FastMCP servers — credentials come from the environment, the
call itself takes no arguments:

```bash
export LULU_ADS_PUBLISHER_ID=pub_123
export LULU_ADS_API_KEY=lk_...
```

```python
mcp.add_middleware(LuluAdsMiddleware())
```

## Quickstart (TypeScript)

```bash
npm install @getlulu/ads
```

```ts
// npm install @getlulu/ads
import { LuluAds } from "@getlulu/ads";
const ads = new LuluAds({ publisherId: "pub_123", apiKey: "lk_..." });
result.sponsored = await ads.sponsoredSlot({ context: { tool: "search_flights" } });
```

## Guarantees (enforced in code, not just promised)

| Guarantee | How |
|---|---|
| A tool call can never break because of ads | every failure path returns `None`/`null`; hard 150ms timeout |
| Always disclosed | `label: "Sponsored"` is set by the SDK and cannot be removed |
| No prompt injection, ever | we ship a data field; there is no display instruction anywhere |
| No PII leaves your server | `context` accepts an allowlisted key set only |
| Quality-gated | every creative passes Dali scoring (≥70) before it can fill a slot |
| Intent, not identity | targeting uses the session's stated intent; no user profiles exist |
| Misconfigured? Still safe | missing creds → client is inert, returns nothing, never crashes |

## Framework adapters

Full details, exclude-lists, and every supported stack: [`docs/integrations.md`](docs/integrations.md).

**LangGraph / LangChain** (`langchain>=1.0`) — middleware, no manual attach step:

```python
from langchain.agents import create_agent
from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

agent = create_agent(model, tools, middleware=[LuluAdsAgentMiddleware()])
```

**CrewAI** (`crewai>=1.9.1`) — one call at startup, before you kick off a crew:

```python
import lulu_ads.integrations.crewai as lulu_crewai
lulu_crewai.install()
```

**TypeScript MCP servers** — wrap the server once, before registering tools:

```ts
import { withLuluAds } from "@getlulu/ads";
withLuluAds(server);
```

**Runtime owners** (chat bots, WhatsApp/Telegram agents, anything that owns
the final message the user sees) — append a disclosed suffix after
generation, as harness code, never as a model instruction:

```python
from lulu_ads import format_suffix
final_message = model_output + format_suffix(sponsored)
```

## Get a publisher ID

Three ways:
- Ask an MCP-connected agent to call the `create_publisher` tool on `https://ads.getlulu.dev/mcp`
- Early beta signup: https://getlulu.dev/publishers
- `POST https://ads.getlulu.dev/publishers` with `{"name", "contact_email", "server_url"}`

See [`docs/quickstart.md`](docs/quickstart.md) for the full walkthrough and
[`docs/contract.md`](docs/contract.md) for the wire-level API.

Docs: https://getlulu.dev/docs · Built by [Lulu](https://getlulu.dev) · Quality gate: [Dali](https://dali.getlulu.dev)
