import { expect, test, vi, afterEach } from "vitest";
import { McpServer } from "skybridge/server";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { z } from "zod";
import { LuluAds } from "../src/index.js";
import { withLuluAdsSkybridge } from "../src/skybridge.js";

const GOOD = { label: "Sponsored", text: "Lulu Ads", url: "https://ads.getlulu.dev/c/x" };

afterEach(() => vi.unstubAllGlobals());

async function connectedPair(server: McpServer, clientName = "t") {
  const [ct, st] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: clientName, version: "0" });
  await Promise.all([server.connect(st), client.connect(ct)]);
  return client;
}

test("withLuluAdsSkybridge attaches sponsored to _meta only, never structuredContent", async () => {
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
  // Never touched -- middleware has no visibility into outputSchema, so
  // structuredContent is left exactly as the tool returned it.
  expect(res.structuredContent).toEqual({ flights: [1] });
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
