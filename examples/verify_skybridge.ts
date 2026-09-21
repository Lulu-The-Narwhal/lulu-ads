/**
 * Proves skybridge_server.ts actually delivers, without a browser or a port.
 *
 *   npx tsx verify_skybridge.ts
 *
 * Connects an in-memory MCP client to the real example server, stubs the ads
 * backend so a slot always fills, and checks where `sponsored` lands for both
 * tool shapes. Exits non-zero on any failure so it works in CI.
 */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";

const AD = { label: "Sponsored", text: "Demo advertiser", url: "https://ads.getlulu.dev/c/demo" };

// Fill every slot, and prove no real network call is needed.
process.env.LULU_ADS_PUBLISHER_ID = "pub_demo";
process.env.LULU_ADS_API_KEY = "lk_demo";
const realFetch = globalThis.fetch;
globalThis.fetch = (async (url: any, init: any) => {
  if (String(url).includes("/slot")) return new Response(JSON.stringify(AD), { status: 200 });
  return realFetch(url, init);
}) as typeof fetch;

const { server } = await import("./skybridge_server.js");

const [ct, st] = InMemoryTransport.createLinkedPair();
const client = new Client({ name: "claude-code", version: "1.0.0" });
await Promise.all([(server as any).connect(st), client.connect(ct)]);

let failures = 0;
function check(label: string, ok: boolean, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}${detail && !ok ? ` — ${detail}` : ""}`);
  if (!ok) failures++;
}

const flights: any = await client.callTool({
  name: "search_flights",
  arguments: { origin: "TLV", destination: "JFK" },
});
check("schemaless tool: sponsored delivered into structuredContent",
  flights.structuredContent?.sponsored?.label === "Sponsored",
  JSON.stringify(flights.structuredContent));
check("schemaless tool: original data preserved",
  Array.isArray(flights.structuredContent?.flights) && flights.structuredContent.flights.length === 3);
check("schemaless tool: _meta mirror also set",
  !!flights._meta?.["ads.getlulu.dev/sponsored"]);

const fare: any = await client.callTool({ name: "fare_summary", arguments: { origin: "TLV" } });
check("schema'd tool: structuredContent NOT polluted (would fail validation)",
  fare.structuredContent && !("sponsored" in fare.structuredContent),
  JSON.stringify(fare.structuredContent));
check("schema'd tool: still monetized via _meta",
  !!fare._meta?.["ads.getlulu.dev/sponsored"]);

console.log(failures === 0 ? "\nAll checks passed." : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
