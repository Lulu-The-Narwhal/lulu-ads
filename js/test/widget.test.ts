import { expect, test } from "vitest";
import { createHash } from "node:crypto";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { claudeAppsDomain, sponsoredWidgetHtml, registerSponsoredWidget } from "../src/widget.js";

async function connectedPair(server: McpServer) {
  const [ct, st] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: "t", version: "0" });
  await Promise.all([server.connect(st), client.connect(ct)]);
  return client;
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
  const appMeta = registerSponsoredWidget(server, {
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
