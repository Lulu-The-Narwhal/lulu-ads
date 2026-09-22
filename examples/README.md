# Examples

Runnable, end-to-end examples of the `lulu-ads` integration. Each file is a
complete program with one demo tool — the monetization is a single line.

Every example runs with **no credentials set**. That is the point: with
`LULU_ADS_PUBLISHER_ID` / `LULU_ADS_API_KEY` unset, the SDK is inert — it
never raises, never calls the network, and your tool result comes back
unmodified. Monetization is opt-in.

| File | Stack | Integration line |
|---|---|---|
| `fastmcp_server.py` | FastMCP (Python) | `mcp.add_middleware(LuluAdsMiddleware())` |
| `typescript_tool.ts` | MCP TypeScript SDK | `withLuluAds(server)` |
| `langgraph_agent.py` | LangChain / LangGraph | see file |
| `crewai_crew.py` | CrewAI | see file |
| `skybridge_server.ts` | Skybridge | `withLuluAdsSkybridge(server)` |

## Skybridge

Skybridge needs its own adapter: `withLuluAds` would misread a Skybridge
server, because Skybridge's `registerTool` takes `(config, handler)` with
`name` folded into config, not the official SDK's `(name, config, handler)`.

```bash
npm install
npm run start:skybridge     # serves on :3000/mcp
npm run verify:skybridge    # proves delivery without a browser or a port
```

Where the ad lands depends on the tool, and this is the part worth knowing:

| Tool shape | `sponsored` goes to | Why |
|---|---|---|
| no `outputSchema` | `structuredContent` **and** `_meta` | views render from structuredContent |
| has `outputSchema` | `_meta` only | an unlisted field would fail the client's validation and break the call |
| registered *before* `withLuluAdsSkybridge` | `_meta` only | schema status unknown — safe default, never a guess |

`verify_skybridge.ts` asserts all of that against the real server over an
in-memory transport, and exits non-zero on failure, so it works in CI.

### Rendering the card

There are two card paths in this SDK and only one of them fits Skybridge:

| | what it is | use it when |
|---|---|---|
| `sponsoredWidgetHtml()` (`lulu-ads/widget`) | a **complete HTML document** — 276KB, of which 243KB is the MCP Apps runtime bridge and ~1.9KB is markup. Six templates (`card`, `banner`, `flip-card`, `scratch-reveal`, `spin`, `hero`). | the host serves it whole as an MCP Apps resource / iframe, e.g. via `enableLuluAds` on Claude or ChatGPT |
| render it in your view | ~40 lines of JSX over the `sponsored` object | **Skybridge** |

`enableLuluAds` is not available on Skybridge: it needs a public
`registerResource`, and Skybridge's `registerViewResource` is private. That is
not a gap to work around — a Skybridge view **is** an MCP Apps resource and
already has that runtime, so injecting a second full document would ship the
machinery twice for 1.9KB of markup.

So on Skybridge: take the data, draw the card. The reference view does it in
about 40 lines.

`skybridge-views/FlightResults.tsx` is the reference view: a results **table**
plus the sponsored **card**, reading `structuredContent.sponsored` and falling
back to `_meta` so one view covers both tool shapes. In a real app it lives in
your `src/views/` directory and Skybridge's Vite plugin builds it; the tool's
`view: { component: "FlightResults" }` binds them.

## Python

```bash
pip install -r requirements.txt
python fastmcp_server.py
```

`requirements.txt` installs `lulu-ads` + `fastmcp`. The LangGraph and CrewAI
examples need their own framework — the file lists it, and the commented
lines in `requirements.txt` cover both.

## TypeScript

```bash
npm install
npm start          # compiles to dist/ then runs (Node >= 18)
```

`npm start` is `npm run build && node dist/typescript_tool.js`. Use
`npm run typecheck` to compile without emitting.

## Turning monetization on

```bash
export LULU_ADS_PUBLISHER_ID=pub_...
export LULU_ADS_API_KEY=lk_...
```

Credentials come from [getlulu.dev/publishers](https://getlulu.dev/publishers),
or by asking an agent to call `create_publisher` on the Lulu Ads MCP server.
See [`../docs/quickstart.md`](../docs/quickstart.md).

Once configured, a filled slot adds a `sponsored` field to the tool result
(TypeScript MCP servers receive it at `_meta["ads.getlulu.dev/sponsored"]`).

**That field is data returned to the model.** It is disclosed to the model as
sponsored content. It is not automatically rendered to the end user, and it is
not an instruction — the SDK ships data, never directives. If you want the user
to see it, that is your decision and your code, and disclosing it as sponsored
is your responsibility.

A missing `sponsored` field is normal and never an error: no campaign matched,
the client is unconfigured, or the backend didn't answer in time. The SDK is
fail-open by design — your tool must never break because an ad didn't fill.
