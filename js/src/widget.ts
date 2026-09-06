/**
 * MCP Apps UI widget helper for the official TypeScript MCP SDK.
 *
 * Turns the plain `sponsored` data field into an actual rendered card in
 * hosts that support the MCP Apps extension (io.modelcontextprotocol/ui),
 * instead of relying on the model's own judgment to format raw JSON nicely.
 * The plain field always stays too — every host that doesn't support MCP
 * Apps yet gets the harmless data fallback; this is additive, not a
 * replacement. Port of python/lulu_ads/widget.py — keep both in sync.
 *
 * Getting a host to actually place the iframe takes two things beyond
 * spec-correct registration (undocumented, self-computable, reverse-engineered
 * from community reports against modelcontextprotocol/ext-apps#671 — not
 * official docs, verify against your own host):
 *
 *   1. Claude requires `_meta.ui.domain` == sha256(<your MCP endpoint URL,
 *      including the /mcp path>)[:32] + ".claudemcpcontent.com". Missing or
 *      wrong domain: Claude fetches the resource, claims a widget rendered,
 *      and never shows it. Deterministic — both sides compute it
 *      independently, it is not a credential exchange.
 *   2. The widget HTML must send `ui/notifications/initialized` via
 *      postMessage on load. The host keeps the iframe reserved-but-hidden
 *      until it receives that message.
 *
 * A third, easy to miss entirely because it fails silently: the widget
 * iframe's own CSP only allows `img-src 'self' data: <resourceDomains>`
 * (MCP Apps spec). Point `logo` at your own CDN and nothing in the
 * registration flow tells you it's blocked -- the card just renders with no
 * logo, forever, in every host, no console error to find. `logo` is fetched
 * right here at registration time and inlined as a `data:` URI instead,
 * which `img-src` always allows -- no `resourceDomains` config, no
 * dependency on your logo's host staying reachable from the widget's
 * sandbox. This is why `logo` takes a URL to fetch rather than a URL to
 * embed directly, and why registration is async now.
 *
 * Usage:
 *
 *   import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
 *   import { registerSponsoredWidget } from "lulu-ads/widget";
 *
 *   const server = new McpServer({ name: "my-server", version: "1.0.0" });
 *   const appMeta = await registerSponsoredWidget(server, {
 *     endpointUrl: "https://my-server.example.com/mcp",
 *     text: "Save 15% at checkout",
 *     url: "https://example.com/deal",
 *     logo: "https://example.com/logo.png", // optional; fetched + inlined
 *   });
 *
 *   server.registerTool("search", { ...appMeta }, handler);
 *
 * `endpointUrl` must be the exact public MCP connector URL clients connect
 * to. `resourceUri` itself is still registered once, statically, at
 * startup — but the compiled widget bundle now *listens* for the live
 * `ui/notifications/tool-result` message the MCP Apps host sends on every
 * tool call (a fresh iframe per call is already how the protocol works;
 * nothing server-side had to change) and swaps its content to that call's
 * real `structuredContent.sponsored` data. The widget starts in a loading
 * skeleton and only ever renders ad content once a live `tool-result`
 * arrives — `text`/`url`/`logoDataUri` passed here are NOT rendered as
 * initial content; a host that mounts the iframe but never pushes
 * `tool-result` shows the skeleton indefinitely, not a fallback ad.
 * `label`/`cta`/`accent*` are the only fields the live path actually uses
 * from these options: defaults for fields the wire payload doesn't carry
 * (`cta`, never; `label`, when omitted) and the static per-integrator
 * brand theme respectively.
 */
import { createHash } from "node:crypto";
import { WIDGET_BUNDLE_HTML } from "./generatedWidgetBundle.js";

const DEFAULT_RESOURCE_URI = "ui://lulu-ads/sponsored.html";
const OPTS_PLACEHOLDER = "__LULU_ADS_OPTS__";

// Registration-time integrator choice, same shape as widgets.ts's
// registerResultWidget's TEMPLATES/template -- baked into the compiled
// bundle's opts blob at registration time, never sent dynamically per
// call. "card" is today's only format; more are added here as their own
// components ship in js/widget-src/ (see LUL-45/LUL-47..57 in Linear).
export const TEMPLATES = ["card"] as const;
export type Template = (typeof TEMPLATES)[number];

// Keeps the inlined data: URI (and the resource payload every client
// downloads) small -- this renders at 28x28 in the card, never a full-size
// asset. Raise only if you know your host's resource-size limits.
const MAX_LOGO_BYTES = 200_000;
const LOGO_FETCH_TIMEOUT_MS = 3_000;
const ALLOWED_LOGO_CONTENT_TYPES = new Set([
  "image/png", "image/jpeg", "image/jpg", "image/svg+xml", "image/webp", "image/gif",
]);

/** Downloads `logoUrl` and returns it as a `data:` URI, or null on any
 * failure (bad status, wrong/missing content-type, oversized, network
 * error, timeout) -- a broken logo must never break the widget or the
 * server registering it, so this never throws. */
export async function fetchLogoDataUri(logoUrl: string): Promise<string | null> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), LOGO_FETCH_TIMEOUT_MS);
    let res: Response;
    try {
      res = await fetch(logoUrl, { signal: controller.signal, redirect: "follow" });
    } finally {
      clearTimeout(timer);
    }
    if (!res.ok) return null;
    const contentType = (res.headers.get("content-type") ?? "").split(";")[0].trim().toLowerCase();
    if (!ALLOWED_LOGO_CONTENT_TYPES.has(contentType)) return null;
    const buf = Buffer.from(await res.arrayBuffer());
    if (buf.length > MAX_LOGO_BYTES) return null;
    return `data:${contentType};base64,${buf.toString("base64")}`;
  } catch {
    return null;
  }
}

// Lulu brand tokens (ads-web/app/globals.css: --lulu-amber / -light / -dark)
const ACCENT = "#E07A00";
const ACCENT_LIGHT = "#F5A623";
const ACCENT_DARK = "#B55E00";

/** The exact `_meta.ui.domain` value Claude expects for an MCP connector's
 * endpoint URL. Deterministic — no registration or credential needed, just
 * the same hash Claude computes on its side. */
export function claudeAppsDomain(endpointUrl: string): string {
  const digest = createHash("sha256").update(endpointUrl).digest("hex").slice(0, 32);
  return `${digest}.claudemcpcontent.com`;
}

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export interface SponsoredWidgetOptions {
  text: string;
  url: string;
  label?: string;
  cta?: string;
  /** Already-resolved `data:` URI -- see `fetchLogoDataUri` / `registerSponsoredWidget`'s
   * `logo` option. A raw `https://` URL here would be silently dropped by the widget
   * sandbox's CSP. */
  logoDataUri?: string;
  accent?: string;
  accentLight?: string;
  accentDark?: string;
  /** Card visual format -- see `TEMPLATES`. Defaults to `"card"`, today's
   * only format. Registration-time integrator choice, not a per-call
   * value. */
  template?: Template;
}

/** Renders the Lulu Ads sponsored-card widget: a floating, rounded,
 * gradient card with a disclosed label, live-swappable per tool call. The
 * markup/CSS/JS themselves come from the compiled `js/widget-src/`
 * React/shadcn build (`generatedWidgetBundle.ts` -- a single self-
 * contained HTML document, everything inlined, no external requests, same
 * discipline the old hand-written template followed for the logo `data:`
 * URI). This function's job is narrower than it used to be: apply the
 * same defaults the old template applied, then substitute the result --
 * as an HTML-attribute-escaped JSON blob, so a malicious `text`/`url`
 * still can't break out of the markup (see the widget-src `index.html`
 * comment on the placeholder element and mcpBridge.ts's
 * `readInitialOptions` for the consuming/decoding side) -- into the
 * bundle's `__LULU_ADS_OPTS__` placeholder. */
export function sponsoredWidgetHtml(opts: SponsoredWidgetOptions): string {
  const {
    text,
    url,
    label = "Sponsored",
    cta = "Learn more →",
    logoDataUri,
    accent = ACCENT,
    accentLight = ACCENT_LIGHT,
    accentDark = ACCENT_DARK,
    template = "card",
  } = opts;

  if (!(TEMPLATES as readonly string[]).includes(template)) {
    throw new Error(`unknown template ${JSON.stringify(template)} -- expected one of ${TEMPLATES.join(", ")}`);
  }

  const resolvedOpts: SponsoredWidgetOptions = {
    text,
    url,
    label,
    cta,
    logoDataUri,
    accent,
    accentLight,
    accentDark,
    template,
  };
  // JSON.stringify drops undefined-valued keys (logoDataUri when absent)
  // on its own -- no extra filtering needed to match the old template's
  // "no <img> element at all when logoDataUri is absent" contract.
  const optsAttr = escapeHtml(JSON.stringify(resolvedOpts));

  // replaceAll, not replace: a plain single-occurrence replace would
  // silently target the wrong match if the placeholder token is ever
  // spelled out again elsewhere in the bundle (e.g. in a comment) --
  // see widget-src/index.html's own comment on this exact gotcha.
  return WIDGET_BUNDLE_HTML.replaceAll(OPTS_PLACEHOLDER, optsAttr);
}

type AnyServer = {
  registerResource: (name: string, uri: string, config: Record<string, unknown>, readCallback: (...args: any[]) => any) => unknown;
};

export interface RegisterSponsoredWidgetOptions extends Omit<SponsoredWidgetOptions, "logoDataUri"> {
  endpointUrl: string;
  /** URL to fetch a brand mark from -- downloaded once, here, at
   * registration time, and inlined into the widget as a `data:` URI (see
   * the module docstring for why a raw remote URL would silently never
   * render). A fetch failure just means no logo in the card, never a
   * registration error. */
  logo?: string;
  resourceUri?: string;
  visibility?: ("app" | "model")[];
}

export interface SponsoredAppMeta {
  _meta: { ui: { resourceUri: string; visibility: ("app" | "model")[] } };
}

/** Registers a rendered MCP Apps UI sponsored-card resource on an MCP
 * server instance and returns the `_meta` to spread onto whichever tool(s)
 * should carry it:
 *
 *   const appMeta = await registerSponsoredWidget(server, { endpointUrl, text, url });
 *   server.registerTool("search", { ...appMeta }, handler);
 */
export async function registerSponsoredWidget(
  server: AnyServer,
  opts: RegisterSponsoredWidgetOptions
): Promise<SponsoredAppMeta> {
  const template = opts.template ?? "card";
  if (!(TEMPLATES as readonly string[]).includes(template)) {
    throw new Error(`unknown template ${JSON.stringify(template)} -- expected one of ${TEMPLATES.join(", ")}`);
  }

  const uri = opts.resourceUri ?? DEFAULT_RESOURCE_URI;
  const domain = claudeAppsDomain(opts.endpointUrl);
  const logoDataUri = opts.logo ? (await fetchLogoDataUri(opts.logo)) ?? undefined : undefined;
  const html = sponsoredWidgetHtml({ ...opts, logoDataUri });

  server.registerResource(
    "sponsored_card",
    uri,
    {
      mimeType: "text/html;profile=mcp-app",
      _meta: { ui: { domain } },
    },
    async () => ({
      contents: [{ uri, mimeType: "text/html;profile=mcp-app", text: html }],
    })
  );

  return { _meta: { ui: { resourceUri: uri, visibility: opts.visibility ?? ["model"] } } };
}
