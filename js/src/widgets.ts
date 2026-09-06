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
 * them): the SPONSORED strip -- a cover card (colorful cover band, a real
 * image when the payload supplies `cover_image_url`, otherwise an animated
 * gradient; logo tile with letter-tile fallback via `sponsored.logo_url`
 * overlapping the seam; CTA; "via Lulu Ads"), the transparent
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

// The SPONSORED strip's own visual template (LUL-69) -- independent of
// `template` above, which picks the result-widget's body layout (NOTE:
// `template: "carousel-card"` is a body layout; this "carousel" is a
// different, unrelated thing -- the footer's own presentation). "card" is
// the default: a cover card (colorful cover band + overlapping logo tile +
// text + CTA), always fully visible. The others port widget.ts's React
// templates into this frame's own vanilla-JS renderer: "flip-card" (a
// teaser with the same cover identity, crossfades to reveal the offer on
// tap), "carousel" (auto-cycles between three framings of the SAME single
// sponsored payload -- a bigger brand logo, the offer text, then the CTA --
// never multiple different sponsors: this frame only ever gets one
// sponsored payload per call, so unlike widget.ts's carousel template
// there is no multi-advertiser rotation here, see LUL-49 for that
// separate, still-blocked, backend question), "scratch-reveal" (canvas
// foil layer over the offer
// text/CTA -- never over the cover band, so "SPONSORED" stays visible
// regardless of scratch state -- auto-reveals after 5s regardless of
// interaction, styled after a lottery scratch ticket but with exactly one
// guaranteed outcome and no "losing" state, which is what keeps it out of
// gambling-mechanic territory despite the visual reference). "banner" is
// still a no-op here (redundant with "card"); the "single row, no room for
// a full-bleed image" reasoning that used to also exclude "hero" no longer
// holds now that the strip itself is cover-height -- worth a follow-up
// ticket, not resolved by this comment. "spin" shipped and was removed in
// the same release cycle -- a coin-flip scaleX on a small, often-flat
// letter-tile logo turned out visually illegible in practice (mid-
// animation it shrinks to a near-invisible sliver against a busy cover
// background); replaced with "carousel" rather than patched, since
// sliding + dots is an unambiguous, widely recognized pattern where "what
// is this animation" was the exact failure mode. Only formats actually
// ported into this frame's own renderSponsored() get added here, not the
// whole standalone gallery automatically.
export const SPONSOR_TEMPLATES = ["card", "flip-card", "carousel", "scratch-reveal"] as const;
export type SponsorTemplate = (typeof SPONSOR_TEMPLATES)[number];

const TEMPLATE_PLACEHOLDER = "__LW_TEMPLATE__";
const SPONSOR_TEMPLATE_PLACEHOLDER = "__LW_SPONSOR_TEMPLATE__";
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
  /** The SPONSORED strip's own visual format -- see `SPONSOR_TEMPLATES`.
   * Independent of `template`, this widget's own body layout. Defaults
   * to `"card"`, the original always-visible strip every existing
   * integrator already gets. */
  sponsorTemplate?: SponsorTemplate;
}

export interface ResultAppMeta {
  _meta: {
    ui: { resourceUri: string; visibility: ("app" | "model")[] };
    "openai/outputTemplate": string;
    "ui/resourceUri": string;
  };
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
  sponsorTemplate?: SponsorTemplate;
}): string {
  const template = opts.template ?? "stat-card";
  if (!(TEMPLATES as readonly string[]).includes(template)) {
    throw new Error(
      `unknown template ${JSON.stringify(template)} -- expected one of ${TEMPLATES.join(", ")}`
    );
  }
  const sponsorTemplate = opts.sponsorTemplate ?? "card";
  if (!(SPONSOR_TEMPLATES as readonly string[]).includes(sponsorTemplate)) {
    throw new Error(
      `unknown sponsor_template ${JSON.stringify(sponsorTemplate)} -- expected one of ${SPONSOR_TEMPLATES.join(", ")}`
    );
  }
  const config: Record<string, unknown> = { mapping: opts.mapping ?? {} };
  if (opts.bodyHtml) config.bodyHtml = opts.bodyHtml;
  const configJson = JSON.stringify(config);
  return RESULT_FRAME_HTML
    .replaceAll(CONFIG_PLACEHOLDER, escapeHtml(configJson))
    .replaceAll(TEMPLATE_PLACEHOLDER, template)
    .replaceAll(SPONSOR_TEMPLATE_PLACEHOLDER, sponsorTemplate);
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
    _meta: {
      ui: { resourceUri: uri, visibility: opts.visibility ?? ["model"] },
      // ChatGPT discovers widget templates from the tool's outputTemplate
      // key — declaring it alongside the MCP Apps key makes the same
      // widget render on both runtimes.
      "openai/outputTemplate": uri,
      // CopilotKit's MCPAppsMiddleware (@ag-ui/mcp-apps-middleware@0.0.3)
      // only recognizes a tool as UI-capable via this FLAT key (discovery
      // filter: `typeof tool._meta?.["ui/resourceUri"] == "string"`) — it
      // never reads the nested `ui.resourceUri` above. Verified 2026-08-25
      // against the real compiled middleware: without it, zero tools are
      // injected and no widget is ever attempted. Additive alongside the
      // other two dialect keys, same pattern as Claude/ChatGPT coexisting.
      "ui/resourceUri": uri,
    },
  };
}
