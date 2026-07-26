import { afterEach, expect, test, vi } from "vitest";
import { createHash } from "node:crypto";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import {
  claudeAppsDomain,
  fetchLogoDataUri,
  sponsoredWidgetHtml,
  registerSponsoredWidget,
} from "../src/widget.js";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function connectedPair(server: McpServer) {
  const [ct, st] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: "t", version: "0" });
  await Promise.all([server.connect(st), client.connect(ct)]);
  return client;
}

/** Pulls the per-call options blob back out of a rendered widget HTML
 * string -- the compiled React bundle now renders its actual card content
 * client-side from this data (see js/widget-src/src/mcpBridge.ts's
 * `readInitialOptions`), so `sponsoredWidgetHtml()`'s returned markup no
 * longer contains a literal `<img class="logo">`/label/etc. the way the
 * old hand-written template did -- this is the equivalent "did the right
 * data make it into the output" check for the new mechanism. Mirrors the
 * browser's own HTML-attribute-value decoding (never innerHTML/eval),
 * same as the real `readInitialOptions` does. */
function extractInjectedOpts(html: string): Record<string, unknown> {
  const match = html.match(/id="lulu-ads-opts"[^>]*\sdata-opts="([^"]*)"/);
  if (!match) throw new Error("no #lulu-ads-opts data-opts attribute found in rendered widget HTML");
  const decoded = match[1]
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&");
  return JSON.parse(decoded);
}

test("claudeAppsDomain matches the deterministic sha256[:32] + suffix format", () => {
  const endpoint = "https://my-server.example.com/mcp";
  const expected = createHash("sha256").update(endpoint).digest("hex").slice(0, 32) + ".claudemcpcontent.com";
  expect(claudeAppsDomain(endpoint)).toBe(expected);
});

test("sponsoredWidgetHtml escapes content and includes the MCP Apps handshake", () => {
  const html = sponsoredWidgetHtml({ text: '<script>alert(1)</script>', url: "https://example.com/deal" });
  expect(html).not.toContain("<script>alert(1)</script>");
  expect(html).toContain("&lt;script&gt;");
  expect(html).toContain("ui/notifications/initialized");
  expect(html).toContain("ui/open-link");
});

test("registerSponsoredWidget registers a readable resource and returns tool _meta", async () => {
  const server = new McpServer({ name: "s", version: "0" });
  const appMeta = await registerSponsoredWidget(server, {
    endpointUrl: "https://my-server.example.com/mcp",
    text: "Save 15%",
    url: "https://example.com/deal",
  });

  expect(appMeta._meta.ui.resourceUri).toBe("ui://lulu-ads/sponsored.html");
  expect(appMeta._meta.ui.visibility).toEqual(["model"]);

  const client = await connectedPair(server);
  const result: any = await client.readResource({ uri: "ui://lulu-ads/sponsored.html" });
  expect(result.contents[0].mimeType).toBe("text/html;profile=mcp-app");
  expect(result.contents[0].text).toContain("Save 15%");
});

test("sponsoredWidgetHtml omits logoDataUri from the injected opts when absent", () => {
  const html = sponsoredWidgetHtml({ text: "deal", url: "https://example.com" });
  const opts = extractInjectedOpts(html);
  expect(opts.logoDataUri).toBeUndefined();
});

test("sponsoredWidgetHtml carries the logoDataUri through to the injected opts when given", () => {
  const html = sponsoredWidgetHtml({
    text: "deal",
    url: "https://example.com",
    logoDataUri: "data:image/png;base64,aGVsbG8=",
  });
  const opts = extractInjectedOpts(html);
  expect(opts.logoDataUri).toBe("data:image/png;base64,aGVsbG8=");
});

test("sponsoredWidgetHtml applies built-in defaults (label, cta, accent) when omitted", () => {
  const html = sponsoredWidgetHtml({ text: "deal", url: "https://example.com" });
  const opts = extractInjectedOpts(html);
  expect(opts.label).toBe("Sponsored");
  expect(opts.cta).toBe("Learn more →");
  expect(opts.accent).toBe("#E07A00");
  expect(opts.accentLight).toBe("#F5A623");
  expect(opts.accentDark).toBe("#B55E00");
});

test("sponsoredWidgetHtml carries every option through when all are overridden", () => {
  const html = sponsoredWidgetHtml({
    text: "Save big",
    url: "https://example.com/deal",
    label: "Ad",
    cta: "Shop now",
    logoDataUri: "data:image/png;base64,aGVsbG8=",
    accent: "#111111",
    accentLight: "#222222",
    accentDark: "#000000",
  });
  const opts = extractInjectedOpts(html);
  expect(opts).toEqual({
    text: "Save big",
    url: "https://example.com/deal",
    label: "Ad",
    cta: "Shop now",
    logoDataUri: "data:image/png;base64,aGVsbG8=",
    accent: "#111111",
    accentLight: "#222222",
    accentDark: "#000000",
  });
});

test("sponsoredWidgetHtml is genuinely self-contained (no external script/link references)", () => {
  const html = sponsoredWidgetHtml({ text: "deal", url: "https://example.com" });
  expect(html).not.toMatch(/<script[^>]*\ssrc=/);
  expect(html).not.toMatch(/<link[^>]*\shref=/);
  // A <script> with the compiled React/bridge code is still expected --
  // just inlined, not referenced.
  expect(html).toMatch(/<script type="module"[^>]*>[\s\S]+<\/script>/);
});

test("fetchLogoDataUri inlines a small allowed image", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: { "content-type": "image/png" } }))
  );
  const result = await fetchLogoDataUri("https://example.com/logo.png");
  expect(result).toMatch(/^data:image\/png;base64,/);
});

test("fetchLogoDataUri rejects a disallowed content-type", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("<html></html>", { status: 200, headers: { "content-type": "text/html" } }))
  );
  expect(await fetchLogoDataUri("https://example.com/not-an-image")).toBeNull();
});

test("fetchLogoDataUri rejects an oversized image", async () => {
  const big = new Uint8Array(200_001);
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(big, { status: 200, headers: { "content-type": "image/png" } }))
  );
  expect(await fetchLogoDataUri("https://example.com/huge.png")).toBeNull();
});

test("fetchLogoDataUri rejects a non-200 response", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(null, { status: 404 }))
  );
  expect(await fetchLogoDataUri("https://example.com/missing.png")).toBeNull();
});

test("fetchLogoDataUri never throws on a network error", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new Error("boom");
    })
  );
  expect(await fetchLogoDataUri("https://example.com/logo.png")).toBeNull();
});

test("registerSponsoredWidget inlines a fetched logo into the widget", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: { "content-type": "image/png" } }))
  );
  const server = new McpServer({ name: "s-logo", version: "0" });
  await registerSponsoredWidget(server, {
    endpointUrl: "https://my-server.example.com/mcp",
    text: "Save 15%",
    url: "https://example.com/deal",
    logo: "https://example.com/logo.png",
  });

  const client = await connectedPair(server);
  const result: any = await client.readResource({ uri: "ui://lulu-ads/sponsored.html" });
  const opts = extractInjectedOpts(result.contents[0].text);
  expect(opts.logoDataUri).toMatch(/^data:image\/png;base64,/);
});

test("registerSponsoredWidget still registers when the logo fetch fails", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(null, { status: 500 }))
  );
  const server = new McpServer({ name: "s-bad-logo", version: "0" });
  await registerSponsoredWidget(server, {
    endpointUrl: "https://my-server.example.com/mcp",
    text: "Save 15%",
    url: "https://example.com/deal",
    logo: "https://example.com/broken.png",
  });

  const client = await connectedPair(server);
  const result: any = await client.readResource({ uri: "ui://lulu-ads/sponsored.html" });
  const opts = extractInjectedOpts(result.contents[0].text);
  expect(opts.logoDataUri).toBeUndefined();
  expect(opts.text).toBe("Save 15%");
});
