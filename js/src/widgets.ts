/**
 * Result-widget template gallery for the official TypeScript MCP SDK.
 *
 * Most publishers shouldn't design UI. This module ships four predefined,
 * host-native-quality result widgets -- pick a template, map your tool's
 * `structuredContent` fields into it; the frame, design tokens, and the
 * disclosed SPONSORED strip are fixed by the SDK:
 *
 *   import { registerResultWidget } from "lulu-ads/widgets";
 *
 *   const appMeta = registerResultWidget(server, "get_weather", {
 *     template: "stat-card",
 *     mapping: {
 *       eyebrow: "location.name",
 *       value: { path: "temperature_c", suffix: "°" },
 *       condition: "conditions",
 *       chips: [{ path: "humidity_pct", prefix: "💧 ", suffix: "%" }],
 *       atmosphere: "weather_code",
 *     },
 *     endpointUrl: "https://my-server.example.com/mcp",
 *   });
 *   server.registerTool("get_weather", { ...appMeta, ... }, handler);
 *
 * Templates: `stat-card` (big value + chips + optional condition-keyed
 * atmospheric background), `table-card` (headed rows, mono numerics,
 * best-row highlight), `notice-card` (verdict glyph + detail rows),
 * `carousel-card` (3-8 swipeable option cards). `bodyHtml` is the custom
 * escape hatch: static HTML composed ONLY of the `.lw-*` primitives,
 * rendered inside the same frame.
 *
 * Non-negotiables baked into the frame (the body cannot remove or restyle
 * them): the SPONSORED strip (orange rail, logo tile with letter-tile
 * fallback via `sponsored.logo_url`, CTA, "via Lulu Ads"), the transparent
 * `color-scheme: light dark` canvas, and the proven-in-Claude host bridge
 * (`ui/notifications/initialized`, `size-changed`, `tool-result`,
 * `ui/open-link`).
 *
 * Port of python/lulu_ads/widgets.py -- the frame itself is generated from
 * the Python source by scripts/sync-result-frame.mjs so the two SDKs can't
 * drift; keep the registration logic here in sync by hand.
 */
import { claudeAppsDomain, escapeHtml } from "./widget.js";
import { RESULT_FRAME_HTML } from "./resultFrame.js";

export const TEMPLATES = [
  "stat-card",
  "table-card",
  "notice-card",
  "carousel-card",
] as const;
export type ResultTemplate = (typeof TEMPLATES)[number];

const TEMPLATE_PLACEHOLDER = "__LW_TEMPLATE__";
const CONFIG_PLACEHOLDER = "__LW_CONFIG__";

/** A mapping entry: a dot-path string ("location.name") or a path with
 * literal prefix/suffix ({ path: "humidity_pct", prefix: "💧 ", suffix: "%" }). */
export type MappingEntry = string | { path: string; prefix?: string; suffix?: string };

export interface ResultWidgetMapping {
  [key: string]: unknown;
}

export interface ResultWidgetOptions {
  template?: ResultTemplate;
  mapping?: ResultWidgetMapping;
  endpointUrl: string;
  bodyHtml?: string;
  resourceUri?: string;
  visibility?: ("app" | "model")[];
}

export interface ResultAppMeta {
  _meta: { ui: { resourceUri: string; visibility: ("app" | "model")[] } };
}

// Minimal structural type; matches widget.ts's AnyServer approach so the
// helper works across MCP SDK minor versions without a hard peer range.
type AnyServer = {
  registerResource: (
    name: string,
    uri: string,
    config: Record<string, unknown>,
    readCallback: (...args: unknown[]) => unknown
  ) => unknown;
};

/** Builds the self-contained widget HTML for one tool: the shared frame
 * with this tool's template + mapping substituted in. Exposed separately
 * from registration for tests and snapshotting. */
export function resultWidgetHtml(opts: {
  template?: ResultTemplate;
  mapping?: ResultWidgetMapping;
  bodyHtml?: string;
}): string {
  const template = opts.template ?? "stat-card";
  if (!(TEMPLATES as readonly string[]).includes(template)) {
    throw new Error(
      `unknown template ${JSON.stringify(template)} -- expected one of ${TEMPLATES.join(", ")}`
    );
  }
  const config: Record<string, unknown> = { mapping: opts.mapping ?? {} };
  if (opts.bodyHtml) config.bodyHtml = opts.bodyHtml;
  const configJson = JSON.stringify(config);
  return RESULT_FRAME_HTML
    .replaceAll(CONFIG_PLACEHOLDER, escapeHtml(configJson))
    .replaceAll(TEMPLATE_PLACEHOLDER, template);
}

/**
 * Registers a predefined result widget for `tool` and returns the `_meta`
 * to spread onto that tool's registration -- spreading it deliberately
 * replaces `enableLuluAds`'s generic sponsored-card widget for this tool;
 * the sponsored DATA field still flows from the wrapper and renders inside
 * this widget as the fixed disclosed strip:
 *
 *   const appMeta = registerResultWidget(server, "search", { template: "table-card", ... });
 *   server.registerTool("search", { ...appMeta, description, inputSchema }, handler);
 */
export function registerResultWidget(
  server: AnyServer,
  tool: string,
  opts: ResultWidgetOptions
): ResultAppMeta {
  const uri = opts.resourceUri ?? `ui://lulu-ads/result-${tool}.html`;
  const domain = claudeAppsDomain(opts.endpointUrl);
  const html = resultWidgetHtml(opts);

  server.registerResource(
    `result_widget_${tool}`,
    uri,
    {
      mimeType: "text/html;profile=mcp-app",
      // csp: MCP Apps hosts default to img-src 'self' data: — declaring
      // the ads origin lets the rendered-impression beacon (1px <img>)
      // actually load on claude.ai's sandboxed widget origin.
      _meta: {
        ui: {
          domain,
          csp: {
            resourceDomains: ["https://ads.getlulu.dev"],
            connectDomains: ["https://ads.getlulu.dev"],
          },
        },
        // ChatGPT's runtime reads its own CSP field (snake_case) — without
        // it the beacon pixel is sandbox-blocked there.
        "openai/widgetCSP": {
          connect_domains: ["https://ads.getlulu.dev"],
          resource_domains: ["https://ads.getlulu.dev"],
        },
      },
    },
    async () => ({
      contents: [{
        uri,
        mimeType: "text/html;profile=mcp-app",
        text: html,
        _meta: {
          ui: {
            csp: {
              resourceDomains: ["https://ads.getlulu.dev"],
              connectDomains: ["https://ads.getlulu.dev"],
            },
          },
          "openai/widgetCSP": {
            connect_domains: ["https://ads.getlulu.dev"],
            resource_domains: ["https://ads.getlulu.dev"],
          },
        },
      }],
    })
  );

  return {
    _meta: { ui: { resourceUri: uri, visibility: opts.visibility ?? ["model"] } },
  };
}
