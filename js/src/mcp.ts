/**
 * withLuluAds(server, ads?, opts?) — wraps McpServer.registerTool so every tool
 * registered AFTER this call gains a sponsored data field on its results.
 * The official TS SDK has no middleware hook (typescript-sdk#1238), so this
 * proxies registration. structuredContent gets `sponsored` (skipped when the
 * tool declares an outputSchema that would reject it — _meta is the always-safe
 * mirror: `_meta["ads.getlulu.dev/sponsored"]`).
 *
 * `ads` is optional — omit it to get an env-driven `new LuluAds({})`, which is
 * inert (never throws, always resolves null) if creds aren't set.
 */
import { LuluAds } from "./index.js";
import type { Sponsored } from "./index.js";
import { formatCliCard, isCliClient } from "./cliCard.js";

type AnyServer = {
  registerTool: (...args: any[]) => any;
  server?: { getClientVersion?: () => { name?: string } | undefined };
};

export function withLuluAds<S extends AnyServer>(
  server: S,
  ads?: LuluAds,
  opts?: { excludeTools?: string[]; timeoutMs?: number }
): S {
  const client = ads ?? new LuluAds({});
  const exclude = new Set(opts?.excludeTools ?? []);
  const orig = server.registerTool.bind(server);
  (server as AnyServer).registerTool = (name: string, config: any, handler: any) =>
    orig(name, config, async (...args: any[]) => {
      const result = await handler(...args);
      try {
        if (exclude.has(name) || result?.isError) return result;
        const sponsored: Sponsored | null = await client.sponsoredSlot({
          context: { tool: name },
          timeoutMs: opts?.timeoutMs,
        });
        if (!sponsored) return result;
        result._meta = { ...(result._meta ?? {}), "ads.getlulu.dev/sponsored": sponsored };
        const clientName = server.server?.getClientVersion?.()?.name;
        if (isCliClient(clientName)) {
          // Terminals have no widget surface — append a bordered plain-text
          // card to content[] so it reads as distinct from a plain sentence,
          // without touching the model's own words.
          result.content = [
            ...(result.content ?? []),
            { type: "text", text: formatCliCard(sponsored) },
          ];
        }
        if (
          result.structuredContent &&
          typeof result.structuredContent === "object" &&
          !("sponsored" in result.structuredContent) &&
          !config?.outputSchema
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
