import { expect, test, vi, afterEach } from "vitest";
import * as SB from "skybridge/server";
const { McpServer } = SB;
// skybridge 2.x introduced a top-level Skybridge app and moved protocol
// middleware wiring out of McpServer.connect() into the app's request path
// (protocolMiddlewareEntries() is consumed by dist/server/app.js). So on 2.x a
// bare `new McpServer(...).connect(transport)` never applies mcpMiddleware and
// every ad assertion below would fail for harness reasons, not product ones.
// connectedPair therefore wraps the server in a Skybridge app when that class
// exists, and connects directly when it doesn't. One suite, both majors.
const Skybridge: any = (SB as any).Skybridge;
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { z } from "zod";
import { LuluAds } from "../src/index.js";
import { withLuluAdsSkybridge } from "../src/skybridge.js";

const GOOD = { label: "Sponsored", text: "Lulu Ads", url: "https://ads.getlulu.dev/c/x" };

afterEach(() => vi.unstubAllGlobals());

async function connectedPair(server: any, clientName = "t") {
  const [ct, st] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: clientName, version: "0" });
  const target = Skybridge
    ? new Skybridge({ name: "s", version: "0", handler: () => server })
    : server;
  await Promise.all([target.connect(st), client.connect(ct)]);
  return client;
}

test("withLuluAdsSkybridge attaches sponsored to _meta and (schemaless) structuredContent", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAdsSkybridge(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }));
  server.registerTool(
    { name: "search_flights", inputSchema: { origin: z.string() } },
    async ({ origin }) => ({
      content: `flights from ${origin}`,
      structuredContent: { flights: [1] },
    })
  );
  const client = await connectedPair(server);
  const res: any = await client.callTool({ name: "search_flights", arguments: { origin: "TLV" } });
  expect(res._meta["ads.getlulu.dev/sponsored"]).toEqual(GOOD);
  // BEHAVIOR CHANGE (2.0.1), the reason this is a major: this adapter used to
  // be _meta-only, which on Skybridge meant the slot was fetched and never
  // surfaced -- no widget, no CLI card, nothing reading _meta. The tool here
  // declares inputSchema but no outputSchema, so adding `sponsored` cannot
  // fail anyone's output validation and it becomes deliverable.
  expect(res.structuredContent).toEqual({ flights: [1], sponsored: GOOD });
});

test("ads down -> result untouched", async () => {
  vi.stubGlobal("fetch", async () => { throw new TypeError("down"); });
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAdsSkybridge(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }));
  server.registerTool({ name: "t" }, async () => ({ structuredContent: { a: 1 } }));
  const client = await connectedPair(server);
  const res: any = await client.callTool({ name: "t", arguments: {} });
  expect(res.structuredContent).toEqual({ a: 1 });
  expect(res._meta?.["ads.getlulu.dev/sponsored"]).toBeUndefined();
});

test("excludeTools skips a named tool", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAdsSkybridge(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }), {
    excludeTools: ["t"],
  });
  server.registerTool({ name: "t" }, async () => ({ structuredContent: { a: 1 } }));
  const client = await connectedPair(server);
  const res: any = await client.callTool({ name: "t", arguments: {} });
  expect(res._meta?.["ads.getlulu.dev/sponsored"]).toBeUndefined();
});

test("isError result is never touched", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAdsSkybridge(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }));
  server.registerTool({ name: "t" }, async () => ({
    content: "boom",
    isError: true,
  }));
  const client = await connectedPair(server);
  const res: any = await client.callTool({ name: "t", arguments: {} });
  expect(res._meta?.["ads.getlulu.dev/sponsored"]).toBeUndefined();
});

// --- client identity forwarding (0.9.15) -------------------------------
// Skybridge is a second, independent call site. Without these it silently
// shipped impressions with no client identity -- ungateable, so a crawler
// hitting a Skybridge server would look like real billable traffic.

test("withLuluAdsSkybridge forwards the MCP client name as context.client", async () => {
  const bodies: any[] = [];
  vi.stubGlobal("fetch", async (_url: any, init: any) => {
    bodies.push(JSON.parse(init.body));
    return new Response(JSON.stringify(GOOD), { status: 200 });
  });
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAdsSkybridge(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }));
  server.registerTool({ name: "t" }, async () => ({ structuredContent: { a: 1 } }));
  const client = await connectedPair(server, "claude-code");
  await client.callTool({ name: "t", arguments: {} });
  expect(bodies[0].context.client).toBe("claude-code");
  expect(bodies[0].context.tool).toBe("t");
});

test("skybridge: no clientInfo → context omits client, not 'undefined'", async () => {
  const bodies: any[] = [];
  vi.stubGlobal("fetch", async (_url: any, init: any) => {
    bodies.push(JSON.parse(init.body));
    return new Response(JSON.stringify(GOOD), { status: 200 });
  });
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAdsSkybridge(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }));
  server.registerTool({ name: "t" }, async () => ({ structuredContent: { a: 1 } }));
  const client = await connectedPair(server);
  (server as any).server.getClientVersion = () => undefined;
  await client.callTool({ name: "t", arguments: {} });
  expect("client" in bodies[0].context).toBe(false);
  expect(JSON.stringify(bodies[0].context)).not.toContain("undefined");
});

// --- delivery path (2.0.1) ----------------------------------------------
// Before this, Skybridge fetched a slot and surfaced nothing: _meta only,
// no widget (enableLuluAds needs registerResource, which Skybridge doesn't
// expose), no CLI card. structuredContent is what Skybridge renders from.

test("schemaless tool: sponsored is delivered into structuredContent", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAdsSkybridge(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }));
  server.registerTool({ name: "plain" }, async () => ({ structuredContent: { a: 1 } }));
  const client = await connectedPair(server);
  const res: any = await client.callTool({ name: "plain", arguments: {} });
  expect(res.structuredContent.sponsored).toEqual(GOOD);
  expect(res.structuredContent.a).toBe(1);
  expect(res._meta["ads.getlulu.dev/sponsored"]).toEqual(GOOD);
});

test("outputSchema tool: structuredContent untouched, _meta still set", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAdsSkybridge(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }));
  server.registerTool(
    { name: "typed", outputSchema: { a: z.number() } },
    async () => ({ structuredContent: { a: 1 } })
  );
  const client = await connectedPair(server);
  const res: any = await client.callTool({ name: "typed", arguments: {} });
  // Adding an unlisted field would fail the client's schema validation.
  expect(res.structuredContent).toEqual({ a: 1 });
  expect(res._meta["ads.getlulu.dev/sponsored"]).toEqual(GOOD);
});

test("tool registered BEFORE withLuluAdsSkybridge stays _meta-only", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  server.registerTool({ name: "early" }, async () => ({ structuredContent: { a: 1 } }));
  withLuluAdsSkybridge(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }));
  const client = await connectedPair(server);
  const res: any = await client.callTool({ name: "early", arguments: {} });
  // Unknown schema status -> safe default, never a guess.
  expect(res.structuredContent).toEqual({ a: 1 });
  expect(res._meta["ads.getlulu.dev/sponsored"]).toEqual(GOOD);
});
