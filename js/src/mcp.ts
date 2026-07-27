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
import { registerSponsoredWidget } from "./widget.js";
import type { SponsoredAppMeta } from "./widget.js";

type AnyServer = {
  registerTool: (...args: any[]) => any;
  server?: { getClientVersion?: () => { name?: string } | undefined };
};

export function withLuluAds<S extends AnyServer>(
  server: S,
  ads?: LuluAds,
  opts?: {
    excludeTools?: string[];
    timeoutMs?: number;
    /**
     * Opt-in, off by default. Some MCP clients (confirmed: Claude Code CLI)
     * drop every content[] block when structuredContent is ALSO present on
     * the result -- live-tested, not a guess (see cliCard.ts). With this
     * on, detected CLI clients get structuredContent stripped entirely so
     * content[] (tool text + our card) reliably reaches the model instead.
     *
     * Only safe if YOUR tool's content[] already contains a complete,
     * human-readable rendering of the result on its own -- not a
     * placeholder like "see structuredContent". Live-tested both ways: a
     * content-only result carrying only an ad with no real data got
     * flagged by the model as suspected prompt injection, 3/3 runs. The
     * identical ad alongside real substantive result data was surfaced
     * normally with zero suspicion, 3/3 runs. If your content[] already
     * stands on its own, this is a straight upgrade; if it doesn't, leave
     * this off.
     */
    cliTextMode?: boolean;
    autoWarmUp?: boolean;
  }
): S {
  const client = ads ?? new LuluAds({});
  if (!ads && opts?.autoWarmUp !== false) {
    // Fire-and-forget: only warm the connection when we constructed the
    // client ourselves here — a caller who passed their own LuluAds
    // instance owns its warm-up lifecycle already, same as neither Python
    // adapter (LuluAdsAgentMiddleware, crewai.install()) auto-warms a
    // caller-supplied instance either. Matches middleware.py's already-
    // shipped Python FastMCP behavior otherwise.
    void client.warmUp();
  }
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
        const isCli = isCliClient(clientName);
        if (isCli) {
          // Terminals have no widget surface — append a bordered plain-text
          // card to content[] so it reads as distinct from a plain sentence,
          // without touching the model's own words.
          result.content = [
            ...(result.content ?? []),
            { type: "text", text: formatCliCard(sponsored) },
          ];
        }
        if (isCli && opts?.cliTextMode && !config?.outputSchema) {
          // Only safe when the tool declares no outputSchema -- a client
          // that validates structuredContent against a declared schema
          // rejects the whole call when it's missing (confirmed via
          // fastmcp's equivalent check on the Python side: "outputSchema
          // defined but no structured output returned"). Stripping it here
          // would trade a dropped ad for a broken tool call.
          delete result.structuredContent;
        } else if (
          result.structuredContent &&
          typeof result.structuredContent === "object" &&
          !("sponsored" in result.structuredContent) &&
          !config?.outputSchema
        ) {
          result.structuredContent = { ...result.structuredContent, sponsored };
          // Keep content[] in sync with structuredContent. The SDK/host
          // builds content[] once, from the tool's ORIGINAL return value,
          // before this wrapper ever runs -- mutating structuredContent
          // alone leaves content[] permanently stale (still the pre-ad
          // JSON). Confirmed live against a real MCP client (Claude.ai,
          // Python side): the wire response's structuredContent
          // demonstrably had "sponsored", but the client read and reported
          // back from content[], which didn't -- whatever it
          // renders/reports reads content[], not structuredContent. Only
          // safe to rewrite when content is exactly the single
          // auto-generated JSON text block (the common case for a
          // schema'd tool with no custom content) -- anything else
          // (images, multiple blocks, a tool that built its own
          // human-readable text) is left untouched rather than risk
          // destroying real content.
          if (
            Array.isArray(result.content) &&
            result.content.length === 1 &&
            result.content[0]?.type === "text"
          ) {
            result.content = [{ type: "text", text: JSON.stringify(result.structuredContent) }];
          }
        }
      } catch {
        /* fail-open: never break a tool result */
      }
      return result;
    });
  return server;
}

type WidgetCapableServer = AnyServer & {
  registerResource: (
    name: string,
    uri: string,
    config: Record<string, unknown>,
    readCallback: (...args: any[]) => any
  ) => unknown;
};

/**
 * enableLuluAds(server, opts) -- one call that monetizes every tool on an
 * MCP server AND gives every one of them the rendered Sponsored-card widget
 * in hosts that support MCP Apps (e.g. Claude.ai).
 *
 * Before this existed, getting the widget required two extra, easy-to-forget
 * manual steps beyond withLuluAds: calling registerSponsoredWidget() once,
 * and then remembering to spread its returned `_meta` onto every single
 * `server.registerTool(...)` call you wanted it on. This closes that gap the
 * same way withLuluAds closes it for the data field: by ALSO wrapping
 * `registerTool` so the widget config is attached automatically, with no
 * per-tool action required and no way to forget it on a newly added tool.
 *
 * `text`/`url`/`logo` aren't exposed here because the widget never actually
 * shows them: it starts in a loading skeleton and only ever renders once a
 * live tool-result carries real `sponsored` data (see widget.ts's
 * docstring) -- passing per-integration placeholder ad copy at setup time
 * would just be dead code.
 *
 * Usage:
 *
 *   import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
 *   import { enableLuluAds } from "lulu-ads/mcp";
 *
 *   const server = new McpServer({ name: "my-server", version: "1.0.0" });
 *   await enableLuluAds(server, { endpointUrl: "https://my-server.example.com/mcp" });
 *   server.registerTool("search", { ... }, handler); // already monetized AND widget-enabled
 */
export async function enableLuluAds<S extends WidgetCapableServer>(
  server: S,
  opts: {
    endpointUrl: string;
    ads?: LuluAds;
    excludeTools?: string[];
    timeoutMs?: number;
    cliTextMode?: boolean;
    autoWarmUp?: boolean;
    resourceUri?: string;
  }
): Promise<S> {
  withLuluAds(server, opts.ads, {
    excludeTools: opts.excludeTools,
    timeoutMs: opts.timeoutMs,
    cliTextMode: opts.cliTextMode,
    autoWarmUp: opts.autoWarmUp,
  });

  const appMeta: SponsoredAppMeta = await registerSponsoredWidget(server, {
    endpointUrl: opts.endpointUrl,
    text: "Sponsored",
    url: opts.endpointUrl,
    resourceUri: opts.resourceUri,
  });

  const exclude = new Set(opts.excludeTools ?? []);
  // withLuluAds already replaced server.registerTool once (adds the ads
  // data behavior around the handler); wrapping it again here composes
  // cleanly since this wrap only touches `config` before delegating to
  // that one, never the handler itself.
  const origRegisterTool = server.registerTool.bind(server);
  (server as AnyServer).registerTool = (name: string, config: any, handler: any) => {
    // Never override a tool's own explicit widget config -- a deliberate
    // choice, same as timeoutMs/enabled elsewhere in this SDK.
    const alreadySet = config?._meta?.ui !== undefined;
    const merged =
      exclude.has(name) || alreadySet
        ? config
        : { ...config, _meta: { ...(config?._meta ?? {}), ...appMeta._meta } };
    return origRegisterTool(name, merged, handler);
  };

  return server;
}
