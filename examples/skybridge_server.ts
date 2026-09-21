/**
 * Runnable Skybridge server with one-line Lulu Ads monetization.
 *
 *   npm install            # from examples/
 *   npx tsx skybridge_server.ts
 *
 * Skybridge needs its own adapter -- `withLuluAds` (the official-SDK one)
 * would silently misread a Skybridge server, because Skybridge's
 * registerTool takes (config, handler) with `name` folded into config,
 * not the official SDK's (name, config, handler).
 *
 * WHAT LANDS WHERE (this is the part worth understanding):
 *
 *   search_flights  no outputSchema  -> `sponsored` in structuredContent
 *                                       AND _meta. This is the delivering
 *                                       case: a view reads structuredContent.
 *
 *   fare_summary    has outputSchema -> _meta ONLY. Adding an unlisted field
 *                                       to structuredContent would fail the
 *                                       client's own schema validation and
 *                                       break the whole call, so the SDK
 *                                       deliberately doesn't.
 *
 * Both run with NO credentials set: withLuluAdsSkybridge is inert, never
 * throws, never calls the network, and the tools return unmodified. Set
 * LULU_ADS_PUBLISHER_ID / LULU_ADS_API_KEY to turn monetization on
 * (getlulu.dev/publishers).
 */
import { McpServer } from "skybridge/server";
import { z } from "zod";
import { withLuluAdsSkybridge } from "lulu-ads/skybridge";

const server = new McpServer({ name: "skybridge-flights-demo", version: "1.0.0" });

// The whole integration. Call BEFORE registerTool -- only tools registered
// after this are known to be schemaless, and an unknown tool stays _meta-only.
withLuluAdsSkybridge(server);

// Schemaless: rows for a table view, and the sponsored card rides along in
// structuredContent where the view can render it.
server.registerTool(
  {
    name: "search_flights",
    description: "Search flights between two airports (demo data).",
    inputSchema: { origin: z.string(), destination: z.string() },
    view: { component: "FlightResults", description: "Flight results table", prefersBorder: true },
  },
  async ({ origin, destination }) => ({
    structuredContent: {
      origin,
      destination,
      flights: [
        { carrier: "Demo Air", priceUsd: 412, stops: 0 },
        { carrier: "Example Airways", priceUsd: 389, stops: 1 },
        { carrier: "Sample Jet", priceUsd: 501, stops: 0 },
      ],
    },
  })
);

// Typed: outputSchema means structuredContent is validated, so the ad stays
// in _meta only. Shown here so the difference is visible, not theoretical.
server.registerTool(
  {
    name: "fare_summary",
    description: "Cheapest fare on a route (demo data).",
    inputSchema: { origin: z.string() },
    outputSchema: { cheapestUsd: z.number() },
  },
  async () => ({ structuredContent: { cheapestUsd: 389 } })
);

// Exported so verify_skybridge.ts can drive this exact server in-process.
export { server };

// Only bind a port when run directly, never on import.
const runDirectly = import.meta.url === `file://${process.argv[1]}`;
if (runDirectly) server.listen(3000, () => {
  console.log("skybridge-flights-demo on http://localhost:3000/mcp");
  console.log(
    process.env.LULU_ADS_PUBLISHER_ID
      ? "Lulu Ads: configured"
      : "Lulu Ads: inert (no credentials) — tools return unmodified"
  );
});
