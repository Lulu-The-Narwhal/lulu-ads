/**
 * Runnable Skybridge MCP server with one-line Lulu Ads monetization.
 *
 *   npm install
 *   npm run start:skybridge     # serves on :3000/mcp
 *   npm run verify:skybridge    # proves delivery, no browser, no port
 *
 * Written for skybridge 2.x. On 2.x the one-liner goes INSIDE the app
 * handler: 2.x wires protocol middleware through the app's request path, not
 * through McpServer.connect(). Attaching to a bare McpServer you connect
 * yourself registers the middleware into a chain nothing applies -- no error,
 * no ad. lulu-ads >= 0.9.18 warns once if that happens. On skybridge 1.x you
 * attach to the server you connect yourself instead.
 *
 * WHERE THE AD LANDS (Skybridge's middleware can't see a tool's outputSchema):
 *
 *   search_flights  no outputSchema  -> `sponsored` in structuredContent AND
 *                                       _meta. The delivering case: a view
 *                                       renders from structuredContent.
 *   fare_summary    has outputSchema -> _meta ONLY. An unlisted field would
 *                                       fail the client's own validation and
 *                                       break the whole call.
 *
 * A 2.x tool that returns only `content` (no structuredContent at all) also
 * gets the ad -- on _meta. _meta is the one surface present in every case, so
 * a view that reads it covers all three shapes. See skybridge-views/.
 *
 * Runs with NO credentials: withLuluAdsSkybridge is inert, never throws,
 * never calls the network. Set LULU_ADS_PUBLISHER_ID / LULU_ADS_API_KEY to
 * turn monetization on (getlulu.dev/publishers).
 */
import { Skybridge } from "skybridge/server";
import { z } from "zod";
import { withLuluAdsSkybridge } from "lulu-ads/skybridge";

export const app = new Skybridge({
  name: "skybridge-flights-demo",
  version: "1.0.0",
  handler: (server) => {
    // The whole integration. Before registerTool: only tools registered after
    // are known to be schemaless; anything earlier stays _meta-only.
    withLuluAdsSkybridge(server);

    return server
      .registerTool(
        {
          name: "search_flights",
          description: "Search flights between two airports (demo data).",
          inputSchema: { origin: z.string(), destination: z.string() },
          view: { component: "FlightResults", prefersBorder: true },
        },
        async ({ origin, destination }) => ({
          // `content` is required by skybridge 2.x's handler type; the view
          // renders from structuredContent, which is also where the ad lands
          // for a tool with no outputSchema.
          content: `${origin} -> ${destination}`,
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
      )
      .registerTool(
        {
          name: "fare_summary",
          description: "Cheapest fare on a route (demo data).",
          inputSchema: { origin: z.string() },
          outputSchema: { cheapestUsd: z.number() },
        },
        async () => ({ content: "Cheapest fare: $389", structuredContent: { cheapestUsd: 389 } })
      );
  },
});

const runDirectly = import.meta.url === `file://${process.argv[1]}`;
if (runDirectly) {
  await app.run();
  console.log(
    process.env.LULU_ADS_PUBLISHER_ID
      ? "Lulu Ads: configured"
      : "Lulu Ads: inert (no credentials) — tools return unmodified"
  );
}
