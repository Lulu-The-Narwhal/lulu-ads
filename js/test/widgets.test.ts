import { describe, expect, it, vi } from "vitest";

import {
  TEMPLATES,
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

  it("matches the python twin's placeholder wiring", () => {
    // The frame is generated from widgets.py -- if this drifts, re-run
    // scripts/sync-result-frame.mjs.
    const html = resultWidgetHtml({ template: "table-card", mapping: {} });
    expect(html).toContain('getAttribute("data-lw-config")');
    expect(html).not.toContain("__LW_TEMPLATE__");
    expect(html).not.toContain("__LW_CONFIG__");
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

    expect(registerResource).toHaveBeenCalledOnce();
    const [name, uri, config] = registerResource.mock.calls[0];
    expect(name).toBe("result_widget_search");
    expect(uri).toBe("ui://lulu-ads/result-search.html");
    expect((config as { _meta: { ui: { domain: string } } })._meta.ui.domain).toBe(
      claudeAppsDomain("https://example.com/mcp")
    );
  });
});
