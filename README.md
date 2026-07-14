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

[Quickstart](#quickstart) · [Integrations](#framework-integrations) · [Guarantees](#guarantees-enforced-in-code-not-just-promised) · [API contract](docs/contract.md) · [Become a publisher](https://getlulu.dev/publishers)

<img src="https://raw.githubusercontent.com/Lulu-The-Narwhal/lulu-ads/master/assets/lulu-ads-hero.jpg" alt="Lulu, the Lulu Ads narwhal mascot, celebrating on a Tel Aviv billboard — the agent economy has a monetization layer now" width="640" />

`70% to publishers · CPA only · 150ms fail-open · 0 prompt injections, by design`

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
```

```python
from lulu_ads import LuluAds
ads = LuluAds(publisher_id="pub_123", api_key="lk_...")

result = search_flights("TLV", "BKK", dates)
result["sponsored"] = await ads.sponsored_slot(
    context={"tool": "search_flights", "category": "travel.flights"},
    timeout_ms=150,
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
```

```ts
import { LuluAds } from "lulu-ads";
const ads = new LuluAds({ publisherId: "pub_123", apiKey: "lk_..." });
result.sponsored = await ads.sponsoredSlot({ context: { tool: "search_flights" } });
```

No publisher ID yet? See [`docs/quickstart.md`](docs/quickstart.md) — three
ways to get one, none of them gated on the others.

## Framework integrations

| Stack | One-liner | Docs |
|---|---|---|
| FastMCP (Python) | `mcp.add_middleware(LuluAdsMiddleware())` | [→](docs/integrations.md#fastmcp-python) |
| LangChain / LangGraph (Python) | `middleware=[LuluAdsAgentMiddleware()]` | [→](docs/integrations.md#langchain--langgraph-python) |
| CrewAI (Python) | `lulu_crewai.install()` | [→](docs/integrations.md#crewai-python) |
| MCP TS SDK | `withLuluAds(server)` | [→](docs/integrations.md#mcp-servers-typescript) |
| Runtime owners (chat bots, WhatsApp/Telegram agents) | `model_output + format_suffix(sponsored)` | [→](docs/integrations.md#runtime-owners-response-suffix) |
| Any other runtime / language | `sponsored_slot(context)` over the raw contract | [→](docs/integrations.md#any-agent-runtime) |

## Guarantees (enforced in code, not just promised)

| Guarantee | How |
|---|---|
| A tool call can never break because of ads | every failure path returns `None`/`null`; hard 150ms wall-clock timeout |
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
POST /slot  (150ms cap, allowlisted context only)
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
70% publisher / 30% Lulu, on the ledger
```

Full wire-level detail: [`docs/contract.md`](docs/contract.md).

---

Docs: https://getlulu.dev/docs · [Quickstart](docs/quickstart.md) ·
[API contract](docs/contract.md) · [Integrations](docs/integrations.md) ·
[Publisher signup](https://getlulu.dev/publishers) · Quality gate:
[Dali](https://dali.getlulu.dev) · [MIT](LICENSE)
