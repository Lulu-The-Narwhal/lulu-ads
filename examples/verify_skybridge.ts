/**
 * Proves skybridge_server.ts actually delivers, with no browser and no port.
 *
 *   npx tsx verify_skybridge.ts
 *
 * Connects an in-memory MCP client to the real example app, stubs the ads
 * backend so a slot always fills, and checks every delivery surface. Exits
 * non-zero on any failure so it works in CI.
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";

const AD = { label: "Sponsored", text: "Demo advertiser", url: "https://ads.getlulu.dev/c/demo" };

process.env.LULU_ADS_PUBLISHER_ID = "pub_demo";
process.env.LULU_ADS_API_KEY = "lk_demo";
const slotBodies: any[] = [];
const realFetch = globalThis.fetch;
globalThis.fetch = (async (url: any, init: any) => {
  if (String(url).includes("/slot")) {
    slotBodies.push(JSON.parse(init.body));
    return new Response(JSON.stringify(AD), { status: 200 });
  }
  return realFetch(url, init);
}) as typeof fetch;

const { app } = await import("./skybridge_server.js");

const [ct, st] = InMemoryTransport.createLinkedPair();
const client = new Client({ name: "claude-code", version: "1.0.0" });
await Promise.all([(app as any).connect(st), client.connect(ct)]);

let failures = 0;
const check = (label: string, ok: boolean, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${ok ? "" : ` — ${detail}`}`);
  if (!ok) failures++;
};

const flights: any = await client.callTool({
  name: "search_flights",
  arguments: { origin: "TLV", destination: "JFK" },
});
check("no-outputSchema tool: ad delivered into structuredContent",
  flights.structuredContent?.sponsored?.label === "Sponsored",
  JSON.stringify(flights.structuredContent));
check("no-outputSchema tool: original data intact",
  flights.structuredContent?.flights?.length === 3);
check("no-outputSchema tool: _meta mirror set",
  !!flights._meta?.["ads.getlulu.dev/sponsored"]);

const fare: any = await client.callTool({ name: "fare_summary", arguments: { origin: "TLV" } });
check("outputSchema tool: structuredContent NOT polluted",
  fare.structuredContent && !("sponsored" in fare.structuredContent),
  JSON.stringify(fare.structuredContent));
check("outputSchema tool: still monetized via _meta",
  !!fare._meta?.["ads.getlulu.dev/sponsored"]);

// The partnership-critical invariant: client identity must reach /slot, or
// ads-server cannot tell a real agent from a directory crawler.
check("client identity forwarded to /slot",
  slotBodies.every((b) => b.context?.client === "claude-code"),
  JSON.stringify(slotBodies.map((b) => b.context)));
check("tool name forwarded to /slot",
  slotBodies.some((b) => b.context?.tool === "search_flights"));
check("one slot request per tool call, no double-billing",
  slotBodies.length === 2, `got ${slotBodies.length}`);

console.log(failures === 0 ? "\nAll checks passed." : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
