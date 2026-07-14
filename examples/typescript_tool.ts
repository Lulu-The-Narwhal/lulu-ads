/**
 * Runnable MCP TypeScript server with one demo tool, monetized in one line.
 *
 *   npm install lulu-ads @modelcontextprotocol/sdk zod
 *   # add {"type": "module"} to package.json (this file uses ESM `import`)
 *   export LULU_ADS_PUBLISHER_ID=pub_...
 *   export LULU_ADS_API_KEY=lk_...
 *   npx tsx examples/typescript_tool.ts
 *
 * Without the env vars set, withLuluAds(server) is inert: it never throws,
 * never calls fetch, and search_flights just returns unmodified.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { withLuluAds } from "lulu-ads";

const server = new McpServer({ name: "flight-search-demo", version: "1.0.0" });

// Call before registering tools — every tool registered after this gains a
// sponsored data field on its result. Credentials come from
// LULU_ADS_PUBLISHER_ID / LULU_ADS_API_KEY.
withLuluAds(server);

server.registerTool(
  "search_flights",
  {
    description: "Search flights between two airports on a given date (demo data).",
    inputSchema: { origin: z.string(), destination: z.string(), date: z.string() },
  },
  async ({ origin, destination, date }) => ({
    content: [{ type: "text", text: `${origin} -> ${destination} on ${date}` }],
    structuredContent: {
      flights: [
        { carrier: "Demo Air", priceUsd: 412, stops: 0 },
        { carrier: "Example Airways", priceUsd: 389, stops: 1 },
      ],
    },
  })
);

async function main() {
  await server.connect(new StdioServerTransport());
}

main();
