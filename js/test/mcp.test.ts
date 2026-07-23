import { expect, test, vi, afterEach } from "vitest";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { z } from "zod";
import { LuluAds } from "../src/index.js";
import { withLuluAds } from "../src/mcp.js";

const GOOD = { label: "Sponsored", text: "Lulu Ads", url: "https://ads.getlulu.dev/c/x" };

afterEach(() => vi.unstubAllGlobals());

async function connectedPair(server: McpServer) {
  const [ct, st] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: "t", version: "0" });
  await Promise.all([server.connect(st), client.connect(ct)]);
  return client;
}

test("withLuluAds attaches sponsored to structuredContent and _meta", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAds(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }));
  server.registerTool("search_flights", {
    inputSchema: { origin: z.string() },
  }, async ({ origin }) => ({
    content: [{ type: "text", text: origin }],
    structuredContent: { flights: [1] },
  }));
  const client = await connectedPair(server);
  const res: any = await client.callTool({ name: "search_flights", arguments: { origin: "TLV" } });
  expect(res.structuredContent.sponsored).toEqual(GOOD);
  expect(res._meta["ads.getlulu.dev/sponsored"]).toEqual(GOOD);
});

test("ads down → result untouched", async () => {
  vi.stubGlobal("fetch", async () => { throw new TypeError("down"); });
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAds(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }));
  server.registerTool("t", {}, async () => ({ content: [], structuredContent: { a: 1 } }));
  const client = await connectedPair(server);
  const res: any = await client.callTool({ name: "t", arguments: {} });
  expect(res.structuredContent).toEqual({ a: 1 });
});

test("withLuluAds with no ads arg defaults to env-driven inert client (no fetch)", async () => {
  const fetchSpy = vi.fn();
  vi.stubGlobal("fetch", fetchSpy);
  const savedPub = process.env.LULU_ADS_PUBLISHER_ID;
  const savedKey = process.env.LULU_ADS_API_KEY;
  delete process.env.LULU_ADS_PUBLISHER_ID;
  delete process.env.LULU_ADS_API_KEY;
  try {
    const server = new McpServer({ name: "s", version: "0" });
    withLuluAds(server, undefined, { autoWarmUp: false });
    server.registerTool("t", {}, async () => ({ content: [], structuredContent: { a: 1 } }));
    const client = await connectedPair(server);
    const res: any = await client.callTool({ name: "t", arguments: {} });
    expect(res.structuredContent).toEqual({ a: 1 });
    expect(fetchSpy).not.toHaveBeenCalled();
  } finally {
    if (savedPub === undefined) delete process.env.LULU_ADS_PUBLISHER_ID;
    else process.env.LULU_ADS_PUBLISHER_ID = savedPub;
    if (savedKey === undefined) delete process.env.LULU_ADS_API_KEY;
    else process.env.LULU_ADS_API_KEY = savedKey;
  }
});

test("withLuluAds auto-warms the client it constructs itself, by default", async () => {
  const calls: string[] = [];
  vi.stubGlobal("fetch", async (url: string) => {
    calls.push(String(url));
    return new Response("ok");
  });
  process.env.LULU_ADS_PUBLISHER_ID = "pub_1";
  process.env.LULU_ADS_API_KEY = "lk_x";
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAds(server);
  await new Promise((r) => setTimeout(r, 10));
  expect(calls).toEqual(["https://ads.getlulu.dev/health"]);
  delete process.env.LULU_ADS_PUBLISHER_ID;
  delete process.env.LULU_ADS_API_KEY;
});

test("withLuluAds autoWarmUp: false never fires", async () => {
  const calls: string[] = [];
  vi.stubGlobal("fetch", async (url: string) => {
    calls.push(String(url));
    return new Response("ok");
  });
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAds(server, undefined, { autoWarmUp: false });
  await new Promise((r) => setTimeout(r, 10));
  expect(calls).toEqual([]);
});

test("withLuluAds never warms a caller-supplied client", async () => {
  const calls: string[] = [];
  vi.stubGlobal("fetch", async (url: string) => {
    calls.push(String(url));
    return new Response("ok");
  });
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAds(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }));
  await new Promise((r) => setTimeout(r, 10));
  expect(calls).toEqual([]);
});
