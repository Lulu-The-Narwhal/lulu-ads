import { expect, test, vi, afterEach } from "vitest";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { z } from "zod";
import { LuluAds } from "../src/index.js";
import { withLuluAds, enableLuluAds } from "../src/mcp.js";

const ENDPOINT = "https://my-server.example.com/mcp";

const GOOD = { label: "Sponsored", text: "Lulu Ads", url: "https://ads.getlulu.dev/c/x" };

afterEach(() => vi.unstubAllGlobals());

async function connectedPair(server: McpServer, clientName = "t") {
  const [ct, st] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: clientName, version: "0" });
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

test("cli client with cliTextMode gets card appended, structuredContent preserved when outputSchema declared", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAds(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }), { cliTextMode: true });
  server.registerTool("search_flights", {
    inputSchema: { origin: z.string() },
    outputSchema: { flights: z.array(z.number()) },
  }, async () => ({
    content: [{ type: "text", text: "found flights" }],
    structuredContent: { flights: [1] },
  }));
  const client = await connectedPair(server, "claude-code");
  const res: any = await client.callTool({ name: "search_flights", arguments: { origin: "TLV" } });
  // outputSchema declared -> cliTextMode must leave structuredContent exactly
  // as the tool returned it (stripping it would break schema validation);
  // sponsored still reaches the model via the always-safe _meta mirror
  expect(res.structuredContent).toEqual({ flights: [1] });
  expect(res._meta["ads.getlulu.dev/sponsored"]).toEqual(GOOD);
  const cardText = res.content.find((b: any) => b.type === "text" && b.text.includes("via Lulu Ads"));
  expect(cardText).toBeTruthy();
});

test("cli client with cliTextMode strips structuredContent when no outputSchema declared", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAds(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }), { cliTextMode: true });
  server.registerTool("untyped_tool", {}, async () => ({
    content: [{ type: "text", text: "Found 3 flights TLV -> BKK." }],
    structuredContent: { flights: [1] },
  }));
  const client = await connectedPair(server, "claude-code");
  const res: any = await client.callTool({ name: "untyped_tool", arguments: {} });
  expect(res.structuredContent).toBeUndefined();
  const cardText = res.content.find((b: any) => b.type === "text" && b.text.includes("via Lulu Ads"));
  expect(cardText).toBeTruthy();
});

test("non-cli client is unaffected by cliTextMode", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  withLuluAds(server, new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }), { cliTextMode: true });
  server.registerTool("untyped_tool", {}, async () => ({
    content: [{ type: "text", text: "hi" }],
    structuredContent: { flights: [1] },
  }));
  const client = await connectedPair(server, "some-other-client");
  const res: any = await client.callTool({ name: "untyped_tool", arguments: {} });
  expect(res.structuredContent.sponsored).toEqual(GOOD);
  const cardText = res.content.find((b: any) => b.type === "text" && b.text.includes("via Lulu Ads"));
  expect(cardText).toBeUndefined();
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
  expect(calls).toEqual(["https://ads.getlulu.dev/health", "https://ads.getlulu.dev/telemetry/init"]);
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

test("enableLuluAds attaches widget config to a tool registered after the call", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  await enableLuluAds(server, {
    endpointUrl: ENDPOINT,
    ads: new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }),
    autoWarmUp: false,
  });
  server.registerTool("search", { inputSchema: {} }, async () => ({
    content: [{ type: "text", text: "{}" }],
    structuredContent: { flights: [] },
  }));
  const client = await connectedPair(server);
  const { tools }: any = await client.listTools();
  const tool = tools.find((t: any) => t.name === "search");
  expect(tool._meta?.ui?.resourceUri).toBe("ui://lulu-ads/sponsored.html");
});

test("enableLuluAds excluded tool gets no widget config", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  await enableLuluAds(server, {
    endpointUrl: ENDPOINT,
    ads: new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }),
    autoWarmUp: false,
    excludeTools: ["private_tool"],
  });
  server.registerTool("private_tool", { inputSchema: {} }, async () => ({
    content: [{ type: "text", text: "{}" }],
    structuredContent: { secret: true },
  }));
  const client = await connectedPair(server);
  const { tools }: any = await client.listTools();
  const tool = tools.find((t: any) => t.name === "private_tool");
  expect(tool._meta?.ui).toBeUndefined();
});

test("enableLuluAds never overrides a tool's own explicit widget config", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  await enableLuluAds(server, {
    endpointUrl: ENDPOINT,
    ads: new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }),
    autoWarmUp: false,
  });
  server.registerTool("search", {
    inputSchema: {},
    _meta: { ui: { resourceUri: "ui://custom/widget.html", visibility: ["model"] } },
  }, async () => ({
    content: [{ type: "text", text: "{}" }],
    structuredContent: { flights: [] },
  }));
  const client = await connectedPair(server);
  const { tools }: any = await client.listTools();
  const tool = tools.find((t: any) => t.name === "search");
  expect(tool._meta?.ui?.resourceUri).toBe("ui://custom/widget.html");
});

test("enableLuluAds: data and widget both apply end-to-end", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify(GOOD), { status: 200 }));
  const server = new McpServer({ name: "s", version: "0" });
  await enableLuluAds(server, {
    endpointUrl: ENDPOINT,
    ads: new LuluAds({ publisherId: "pub_1", apiKey: "lk_x" }),
    autoWarmUp: false,
  });
  server.registerTool("search", { inputSchema: {} }, async () => ({
    content: [{ type: "text", text: JSON.stringify({ flights: [1] }) }],
    structuredContent: { flights: [1] },
  }));
  const client = await connectedPair(server);
  const res: any = await client.callTool({ name: "search", arguments: {} });
  expect(res.structuredContent.sponsored).toEqual(GOOD);
  const contentJson = JSON.parse(res.content[0].text);
  expect(contentJson.sponsored).toEqual(GOOD);
});
