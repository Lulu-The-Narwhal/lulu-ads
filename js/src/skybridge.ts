/**
 * withLuluAdsSkybridge(server, ads?, opts?) — one-line monetization for
 * Skybridge (https://skybridge.tech) servers.
 *
 * Skybridge's `McpServer` is NOT a drop-in for the official
 * `@modelcontextprotocol/sdk`'s `McpServer` from this SDK's point of view:
 * `registerTool` takes a 2-arg `(config, handler)` shape with `name` folded
 * into `config`, not the official SDK's 3-arg `(name, config, handler)` that
 * `withLuluAds` (./mcp.ts) wraps. Calling `withLuluAds` on a Skybridge server
 * would misread the config object as the tool name and the handler as the
 * config -- silently broken, not a no-op. Confirmed against skybridge@1.4.0's
 * shipped types (dist/server/server.d.ts), not guessed from docs.
 *
 * Skybridge does expose a real hook built for exactly this: protocol-level
 * `mcpMiddleware(filter, handler)`, an onion-model middleware chain (same
 * shape as FastMCP's `on_call_tool` and LangChain's `wrap_tool_call`) rather
 * than a registration-time monkeypatch. This adapter uses that, not
 * `registerTool` wrapping -- confirmed against skybridge@1.4.0's shipped
 * types (dist/server/middleware.d.ts).
 *
 * WORKS ON SKYBRIDGE 1.x AND 2.x, but you attach it differently, because 2.x
 * moved protocol-middleware wiring out of `McpServer.connect()` and into the
 * app's request path (`protocolMiddlewareEntries()` is consumed by
 * skybridge's `dist/server/app.js`). Verified against both majors:
 *
 *   1.x  const server = new McpServer({ ... });
 *        withLuluAdsSkybridge(server);
 *        server.registerTool({ name: "t" }, handler);
 *
 *   2.x  new Skybridge({ name, version, handler: (server) => {
 *          withLuluAdsSkybridge(server);          // inside the handler
 *          return server.registerTool({ name: "t" }, handler);
 *        }});
 *
 * On 2.x, calling this on a bare `new McpServer(...)` that you then
 * `connect()` yourself registers the middleware into a chain nothing ever
 * applies -- no error, no ad, nothing to debug. Attach inside the handler.
 *
 * Deliberately `_meta`-only, never `structuredContent`: `mcpMiddleware`
 * only sees `request.params` (name + arguments) and the result `next()`
 * resolves to -- not the tool's registered `outputSchema`. `withLuluAds`
 * skips a schema'd tool's structuredContent for exactly this reason (an
 * unlisted field fails validation); here there is no way to check that at
 * all, so structuredContent is never touched. `_meta` has no such risk --
 * see ./mcp.ts's docstring, "_meta is the always-safe mirror".
 */
import { LuluAds } from "./index.js";
import type { Sponsored } from "./index.js";

type CallToolResult = {
  content?: unknown;
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
  _meta?: Record<string, unknown>;
};

// STRUCTURAL AND INTENTIONALLY MINIMAL: this declares only the members this
// file uses, so it is NARROWER than the real Skybridge server object. Do not
// read it as an inventory of what is reachable. That mistake has already been
// made once here -- `client` was documented as unreachable on this path, and
// shipped ungateable, purely because this type didn't mention `server`. The
// object had it all along. Before concluding something isn't available,
// probe the installed skybridge build rather than trusting this type.
type SkybridgeServer = {
  // Same optional shape withLuluAds uses in ./mcp.ts. Verified against
  // skybridge's own installed build: inside an mcpMiddleware handler,
  // `server.server.getClientVersion()?.name` returns the connected MCP
  // client ("claude-code"), so this path is real, not assumed. Optional
  // so a server without it still type-checks and simply sends no client.
  server?: { getClientVersion?: () => { name?: string } | undefined };
  // Skybridge's 2-arg shape: (config, handler), with `name` folded into
  // config -- NOT the official SDK's 3-arg (name, config, handler).
  registerTool?: (config: { name?: string; outputSchema?: unknown }, handler: unknown) => unknown;
  mcpMiddleware: (
    filter: string,
    handler: (
      request: { method: string; params: Record<string, unknown> },
      extra: unknown,
      next: () => Promise<unknown>
    ) => Promise<unknown> | unknown
  ) => unknown;
};

export function withLuluAdsSkybridge<S extends SkybridgeServer>(
  server: S,
  ads?: LuluAds,
  opts?: {
    excludeTools?: string[];
    timeoutMs?: number;
    autoWarmUp?: boolean;
    /** See ./mcp.ts's withLuluAds -- same fail-open extra error classifier. */
    isErrorResult?: (result: CallToolResult) => boolean;
  }
): S {
  const client = ads ?? new LuluAds({});
  if (!ads && opts?.autoWarmUp !== false) {
    void client.warmUp();
  }
  const exclude = new Set(opts?.excludeTools ?? []);

  // mcpMiddleware sees only request.params and the result -- never the tool's
  // registered outputSchema. That's why this adapter was _meta-only: writing
  // structuredContent blind can break a schema'd tool, since a client that
  // validates against a declared schema rejects the whole call over an
  // unlisted field. So record the schema flag at REGISTRATION time, where it
  // is visible (skybridge's ToolConfigBase carries outputSchema), and let the
  // middleware consult it. Only tools registered AFTER this call are known --
  // same semantics as withLuluAds in ./mcp.ts -- and an unknown tool stays
  // _meta-only, which is the safe default rather than a guess.
  const schemaless = new Map<string, boolean>();

  // Silent-failure guard. On skybridge 2.x the middleware chain is applied by
  // the app, so attaching to a bare McpServer you connect() yourself wires it
  // into a chain nothing runs: no error, no ad, nothing to debug. Our
  // middleware always runs BEFORE a tool handler in the same call, so if a
  // tool ever executes while this is still false, the middleware is not
  // wired -- which is the one thing we can detect and the one thing worth
  // shouting about. Warned once, never thrown: a misconfigured ad integration
  // must not break somebody's server.
  let middlewareRan = false;
  let warned = false;
  const warnIfUnwired = () => {
    if (middlewareRan || warned) return;
    warned = true;
    try {
      console.warn(
        "[lulu-ads] withLuluAdsSkybridge is attached but its middleware never ran, " +
          "so no sponsored slot will ever be served. On skybridge 2.x, attach it " +
          "INSIDE the app handler:\n" +
          "  new Skybridge({ name, version, handler: (server) => {\n" +
          "    withLuluAdsSkybridge(server);\n" +
          "    return server.registerTool({ name: \"t\" }, handler);\n" +
          "  }});\n" +
          "Attaching to a bare McpServer you connect() yourself works on 1.x only."
      );
    } catch {
      /* a console that throws must not break a tool call */
    }
  };

  const origRegisterTool = server.registerTool?.bind(server);
  if (origRegisterTool) {
    (server as SkybridgeServer).registerTool = (config, handler) => {
      try {
        if (config && typeof config.name === "string") {
          schemaless.set(config.name, !config.outputSchema);
        }
      } catch {
        /* never break tool registration over bookkeeping */
      }
      const wrapped =
        typeof handler === "function"
          ? (...args: unknown[]) => {
              warnIfUnwired();
              return (handler as (...a: unknown[]) => unknown)(...args);
            }
          : handler;
      return origRegisterTool(config, wrapped);
    };
  }

  server.mcpMiddleware("tools/call", async (request, _extra, next) => {
    // Set BEFORE next(): next() runs the tool handler, and the handler is
    // where warnIfUnwired() checks this. Setting it after would make every
    // correctly-wired server warn on its first call.
    middlewareRan = true;
    const result = (await next()) as CallToolResult;
    try {
      const name = request.params?.name;
      if (typeof name !== "string" || exclude.has(name) || result?.isError) return result;
      if (opts?.isErrorResult?.(result)) return result;

      // Read BEFORE the slot call and forward it: ads-server gates serving
      // on `client` so directory crawlers can't manufacture billable
      // impressions. Undefined on a host that never sent clientInfo --
      // sponsoredSlot drops null/undefined, so the key is omitted rather
      // than sent as the string "undefined".
      const clientName = server.server?.getClientVersion?.()?.name;
      const sponsored: Sponsored | null = await client.sponsoredSlot({
        context: { tool: name, client: clientName },
        timeoutMs: opts?.timeoutMs,
      });
      if (!sponsored) return result;

      result._meta = { ...(result._meta ?? {}), "ads.getlulu.dev/sponsored": sponsored };

      // _meta alone has no delivery path here: the SDK registers no widget on
      // Skybridge (enableLuluAds needs a public registerResource, which
      // Skybridge does not expose -- its registerViewResource is private), and
      // there is no CLI card on this adapter. So without this, a Skybridge
      // server fetched a slot, logged it, and surfaced nothing.
      //
      // structuredContent IS the surface Skybridge renders from: probed live,
      // a Skybridge tool result arrives at mcpMiddleware with content[] EMPTY
      // (length 0) and structuredContent populated -- the inverse of the
      // official SDK, where ./mcp.ts must rewrite content[] to keep it in sync.
      // Nothing to sync here, so content[] is deliberately left untouched.
      if (
        schemaless.get(name) === true &&
        result.structuredContent &&
        typeof result.structuredContent === "object" &&
        !("sponsored" in result.structuredContent)
      ) {
        result.structuredContent = { ...result.structuredContent, sponsored };
      }
    } catch {
      /* fail-open: never break a tool result */
    }
    return result;
  });

  return server;
}
