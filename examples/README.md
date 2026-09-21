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
