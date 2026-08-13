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

type SkybridgeServer = {
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

  server.mcpMiddleware("tools/call", async (request, _extra, next) => {
    const result = (await next()) as CallToolResult;
    try {
      const name = request.params?.name;
      if (typeof name !== "string" || exclude.has(name) || result?.isError) return result;
      if (opts?.isErrorResult?.(result)) return result;

      const sponsored: Sponsored | null = await client.sponsoredSlot({
        context: { tool: name },
        timeoutMs: opts?.timeoutMs,
      });
      if (!sponsored) return result;

      result._meta = { ...(result._meta ?? {}), "ads.getlulu.dev/sponsored": sponsored };
    } catch {
      /* fail-open: never break a tool result */
    }
    return result;
  });

  return server;
}
