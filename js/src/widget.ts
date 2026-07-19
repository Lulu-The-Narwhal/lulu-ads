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
 * Usage:
 *
 *   import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
 *   import { registerSponsoredWidget } from "lulu-ads/widget";
 *
 *   const server = new McpServer({ name: "my-server", version: "1.0.0" });
 *   const appMeta = registerSponsoredWidget(server, {
 *     endpointUrl: "https://my-server.example.com/mcp",
 *     text: "Save 15% at checkout",
 *     url: "https://example.com/deal",
 *   });
 *
 *   server.registerTool("search", { ...appMeta }, handler);
 *
 * `endpointUrl` must be the exact public MCP connector URL clients connect
 * to. The card content is fixed at registration time (like a house ad), not
 * re-rendered per tool call — the same tier of sophistication as the
 * plain-JSON fallback's house-fill path. Per-call dynamic ad content in the
 * widget itself is a roadmap item, not implemented here.
 */
import { createHash } from "node:crypto";

const DEFAULT_RESOURCE_URI = "ui://lulu-ads/sponsored.html";

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

function escapeHtml(s: string): string {
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
  accent?: string;
  accentLight?: string;
  accentDark?: string;
}

/** Renders the Lulu Ads sponsored-card widget: a floating, rounded,
 * gradient card with a disclosed label. Ships data baked into markup — no
 * instruction telling any model or host what to do with it. */
export function sponsoredWidgetHtml(opts: SponsoredWidgetOptions): string {
  const {
    text,
    url,
    label = "Sponsored",
    cta = "Learn more →",
    accent = ACCENT,
    accentLight = ACCENT_LIGHT,
    accentDark = ACCENT_DARK,
  } = opts;
  const textHtml = escapeHtml(text);
  const ctaHtml = escapeHtml(cta);
  const urlAttr = escapeHtml(url);
  const labelHtml = escapeHtml(label);

  return `<!doctype html>
<html><head><meta charset="utf-8">
<style>
  :root { color-scheme: light dark; }
  html, body { margin: 0; padding: 0; background: transparent; }
  body { padding: 4px; font-family: -apple-system, "Segoe UI", sans-serif; }
  .card {
    padding: 14px 16px;
    border-radius: 14px;
    background: linear-gradient(135deg, ${accentLight} 0%, ${accent} 55%, ${accentDark} 100%);
    border: 1px solid rgba(255, 255, 255, 0.22);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.22), 0 10px 24px -10px rgba(224, 122, 0, 0.65);
    color: #FFF8EC;
  }
  .label {
    font-size: 10px; font-weight: 800; letter-spacing: .09em;
    text-transform: uppercase; opacity: .92; margin-bottom: 5px;
  }
  .text { font-size: 13px; line-height: 1.45; }
  a { color: #FFFFFF; font-weight: 700; text-decoration: underline; text-underline-offset: 2px; }
  .footer {
    margin-top: 9px; padding-top: 7px;
    border-top: 1px solid rgba(255, 255, 255, 0.25);
    font-size: 10px; opacity: .8;
  }
  .footer a { font-weight: 600; text-decoration: none; }
  .footer a:hover { text-decoration: underline; }
</style></head>
<body>
  <div class="card">
    <div class="label">${labelHtml}</div>
    <div class="text">${textHtml} <a href="${urlAttr}" target="_blank" rel="noopener">${ctaHtml}</a></div>
    <div class="footer">Powered by <a href="https://getlulu.dev" target="_blank" rel="noopener">Lulu Ads</a></div>
  </div>
<script>
  (function () {
    // MCP Apps handshake: the host keeps the iframe reserved-but-hidden until
    // it receives ui/notifications/initialized (modelcontextprotocol/ext-apps#671).
    // Sent on load plus a short fallback timer so a missed load event can't
    // deadlock the widget into permanently-hidden.
    var sent = false;
    function notifyInitialized() {
      if (sent) return;
      sent = true;
      window.parent.postMessage({ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} }, "*");
      var h = document.body.scrollHeight;
      if (h) {
        window.parent.postMessage(
          { jsonrpc: "2.0", method: "ui/notifications/size-changed", params: { width: 400, height: h } },
          "*"
        );
      }
    }
    window.addEventListener("load", notifyInitialized);
    setTimeout(notifyInitialized, 300);

    // Plain <a target="_blank"> clicks get silently swallowed inside the
    // sandboxed MCP Apps iframe (no allow-popups) — right-click "open in
    // new tab" bypasses the iframe's JS entirely, which is why that alone
    // worked. The sanctioned path is ui/open-link, a real JSON-RPC request
    // the host handles outside the sandbox (modelcontextprotocol/ext-apps
    // spec.types.ts: McpUiOpenLinkRequest). href/target stay on the <a> as
    // a harmless fallback for any host that doesn't run this JS.
    document.querySelectorAll("a[href]").forEach(function (link) {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        window.parent.postMessage(
          { jsonrpc: "2.0", id: "open-link-" + Date.now(), method: "ui/open-link", params: { url: link.href } },
          "*"
        );
      });
    });
  })();
</script>
</body></html>`;
}

type AnyServer = {
  registerResource: (name: string, uri: string, config: Record<string, unknown>, readCallback: (...args: any[]) => any) => unknown;
};

export interface RegisterSponsoredWidgetOptions extends SponsoredWidgetOptions {
  endpointUrl: string;
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
 *   const appMeta = registerSponsoredWidget(server, { endpointUrl, text, url });
 *   server.registerTool("search", { ...appMeta }, handler);
 */
export function registerSponsoredWidget(
  server: AnyServer,
  opts: RegisterSponsoredWidgetOptions
): SponsoredAppMeta {
  const uri = opts.resourceUri ?? DEFAULT_RESOURCE_URI;
  const domain = claudeAppsDomain(opts.endpointUrl);
  const html = sponsoredWidgetHtml(opts);

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
