import { describe, expect, it, vi } from "vitest";

import {
  TEMPLATES,
  SPONSOR_TEMPLATES,
  registerResultWidget,
  resultWidgetHtml,
} from "../src/widgets.js";
import { claudeAppsDomain } from "../src/widget.js";

describe("resultWidgetHtml", () => {
  it("renders all four templates", () => {
    for (const template of TEMPLATES) {
      const html = resultWidgetHtml({ template, mapping: { eyebrow: "x" } });
      expect(html).toContain(`var TEMPLATE = "${template}";`);
    }
  });

  it("rejects unknown templates", () => {
    expect(() =>
      resultWidgetHtml({ template: "hero-card" as never, mapping: {} })
    ).toThrow(/unknown template/);
  });

  it("carries the non-negotiables in the frame", () => {
    const html = resultWidgetHtml({ template: "stat-card", mapping: {} });
    expect(html).toContain("color-scheme: light dark");
    expect(html).toContain("ui/notifications/initialized");
    expect(html).toContain("ui/notifications/size-changed");
    expect(html).toContain("ui/notifications/tool-result");
    expect(html).toContain("ui/open-link");
    expect(html).toContain("SPONSORED");
    expect(html).toContain("via Lulu Ads");
    expect(html).toContain("lw-shine");
    expect(html).toContain("prefers-reduced-motion");
    expect(html).toContain("logo_url");
    expect(html).toContain("letterTile");
  });

  it("escapes the mapping into the config attribute", () => {
    const html = resultWidgetHtml({
      template: "stat-card",
      mapping: { eyebrow: 'x"onmouseover="alert(1)' },
    });
    expect(html).not.toContain('x"onmouseover');
    expect(html).toContain("x\\&quot;onmouseover");
  });

  it("embeds the bodyHtml escape hatch in the config", () => {
    const html = resultWidgetHtml({
      template: "stat-card",
      mapping: {},
      bodyHtml: '<div class="lw-value">42</div>',
    });
    expect(html).toContain("bodyHtml");
    expect(html).toContain("lw-value");
  });

  it("embeds the table-card rowLink capability", () => {
    const html = resultWidgetHtml({
      template: "table-card",
      mapping: { rows: "flights", columns: [], rowLink: "booking_url" },
    });
    expect(html).toContain("booking_url");
    expect(html).toContain("rowUrl");
    expect(html).toContain("openLink(String(rowUrl))");
    expect(html).toContain("tr.linked");
  });

  it("matches the python twin's placeholder wiring", () => {
    // The frame is generated from widgets.py -- if this drifts, re-run
    // scripts/sync-result-frame.mjs.
    const html = resultWidgetHtml({ template: "table-card", mapping: {} });
    expect(html).toContain('getAttribute("data-lw-config")');
    expect(html).not.toContain("__LW_TEMPLATE__");
    expect(html).not.toContain("__LW_CONFIG__");
    expect(html).not.toContain("__LW_SPONSOR_TEMPLATE__");
  });
});

describe("sponsor_template (LUL-69)", () => {
  it("defaults to card", () => {
    const html = resultWidgetHtml({ template: "stat-card", mapping: {} });
    expect(html).toContain('var SPONSOR_TEMPLATE = "card";');
  });

  it("renders all sponsor templates", () => {
    for (const sponsorTemplate of SPONSOR_TEMPLATES) {
      const html = resultWidgetHtml({ template: "stat-card", mapping: {}, sponsorTemplate });
      expect(html).toContain(`var SPONSOR_TEMPLATE = "${sponsorTemplate}";`);
    }
  });

  it("rejects an unknown sponsor_template", () => {
    expect(() =>
      resultWidgetHtml({ template: "stat-card", mapping: {}, sponsorTemplate: "hero" as never })
    ).toThrow(/unknown sponsor_template/);
  });

  it("flip-card's front face has a CTA, not just a bare disclosure label", () => {
    const html = resultWidgetHtml({ template: "stat-card", mapping: {}, sponsorTemplate: "flip-card" });
    expect(html).toContain("Tap to reveal");
  });

  it("scratch-reveal ships the canvas markup", () => {
    const html = resultWidgetHtml({ template: "stat-card", mapping: {} });
    expect(html).toContain('id="scratch-canvas"');
  });

  it("carousel ships the track and dots markup", () => {
    const html = resultWidgetHtml({ template: "stat-card", mapping: {} });
    expect(html).toContain('id="carousel-track"');
    expect(html).toContain('id="carousel-dots"');
  });

  it("rejects the removed spin sponsor_template", () => {
    // spin shipped, turned out visually illegible (a coin-flip scaleX on a
    // small, often-flat letter-tile logo shrinks to a near-invisible
    // sliver mid-animation), and was replaced by carousel rather than
    // patched.
    expect(() =>
      resultWidgetHtml({ template: "stat-card", mapping: {}, sponsorTemplate: "spin" as never })
    ).toThrow(/unknown sponsor_template/);
  });
});

describe("registerResultWidget", () => {
  it("registers the resource with the Claude domain and returns spreadable meta", () => {
    const registerResource = vi.fn();
    const server = { registerResource } as never;

    const meta = registerResultWidget(server, "search", {
      template: "table-card",
      mapping: { rows: "items" },
      endpointUrl: "https://example.com/mcp",
    });

    expect(meta._meta.ui.resourceUri).toBe("ui://lulu-ads/result-search.html");
    expect(meta._meta.ui.visibility).toEqual(["model"]);
    expect(meta._meta["openai/outputTemplate"]).toBe("ui://lulu-ads/result-search.html");
    // CopilotKit's MCPAppsMiddleware only discovers UI tools via this flat
    // key -- see the comment above this field in widgets.ts for why.
    expect(meta._meta["ui/resourceUri"]).toBe("ui://lulu-ads/result-search.html");

    expect(registerResource).toHaveBeenCalledOnce();
    const [name, uri, config] = registerResource.mock.calls[0];
    expect(name).toBe("result_widget_search");
    expect(uri).toBe("ui://lulu-ads/result-search.html");
    expect((config as { _meta: { ui: { domain: string } } })._meta.ui.domain).toBe(
      claudeAppsDomain("https://example.com/mcp")
    );
  });
});
