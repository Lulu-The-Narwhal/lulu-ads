"""MCP Apps UI widget helper for FastMCP servers.

Turns the plain `sponsored` data field into an actual rendered card in
hosts that support the MCP Apps extension (io.modelcontextprotocol/ui),
instead of relying on the model's own judgment to format raw JSON nicely.
The plain field always stays too — every host that doesn't support MCP
Apps yet gets the harmless data fallback; this is additive, not a
replacement.

Getting a host to actually place the iframe takes two things beyond
spec-correct registration (undocumented, self-computable, reverse-engineered
from community reports against modelcontextprotocol/ext-apps#671 — not
official docs, verify against your own host):

  1. Claude requires `_meta.ui.domain` == sha256(<your MCP endpoint URL,
     including the /mcp path>)[:32] + ".claudemcpcontent.com". Missing or
     wrong domain: Claude fetches the resource, claims a widget rendered,
     and never shows it. Deterministic — both sides compute it
     independently, it is not a credential exchange.
  2. The widget HTML must send `ui/notifications/initialized` via
     postMessage on load. The host keeps the iframe reserved-but-hidden
     until it receives that message.

Usage:

    from fastmcp import FastMCP
    from lulu_ads.widget import register_sponsored_widget

    mcp = FastMCP("my-server")
    sponsored_app = register_sponsored_widget(
        mcp,
        endpoint_url="https://my-server.example.com/mcp",
        text="Save 15% at checkout",
        url="https://example.com/deal",
    )

    @mcp.tool(app=sponsored_app)
    def search(...): ...

`endpoint_url` must be the exact public MCP connector URL clients connect
to. The card content is fixed at registration time (like a house ad), not
re-rendered per tool call — the same tier of sophistication as the
plain-JSON fallback's house-fill path. Per-call dynamic ad content in the
widget itself is a roadmap item, not implemented here.
"""
from __future__ import annotations

import hashlib
import html as _html

_DEFAULT_RESOURCE_URI = "ui://lulu-ads/sponsored.html"

# Lulu brand tokens (ads-web/app/globals.css: --lulu-amber / -light / -dark)
_ACCENT = "#E07A00"
_ACCENT_LIGHT = "#F5A623"
_ACCENT_DARK = "#B55E00"


def claude_apps_domain(endpoint_url: str) -> str:
    """The exact `_meta.ui.domain` value Claude expects for an MCP
    connector's endpoint URL. Deterministic — no registration or
    credential needed, just the same hash Claude computes on its side.
    """
    digest = hashlib.sha256(endpoint_url.encode()).hexdigest()[:32]
    return f"{digest}.claudemcpcontent.com"


def sponsored_widget_html(
    *,
    text: str,
    url: str,
    label: str = "Sponsored",
    cta: str = "Learn more →",
    accent: str = _ACCENT,
    accent_light: str = _ACCENT_LIGHT,
    accent_dark: str = _ACCENT_DARK,
) -> str:
    """Renders the Lulu Ads sponsored-card widget: a floating, rounded,
    gradient card with a disclosed label. Ships data baked into markup —
    no instruction telling any model or host what to do with it.
    """
    text_html = _html.escape(text)
    cta_html = _html.escape(cta)
    url_attr = _html.escape(url, quote=True)
    label_html = _html.escape(label)
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<style>
  :root {{ color-scheme: light dark; }}
  html, body {{ margin: 0; padding: 0; background: transparent; }}
  body {{ padding: 4px; font-family: -apple-system, "Segoe UI", sans-serif; }}
  .card {{
    padding: 14px 16px;
    border-radius: 14px;
    background: linear-gradient(135deg, {accent_light} 0%, {accent} 55%, {accent_dark} 100%);
    border: 1px solid rgba(255, 255, 255, 0.22);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.22), 0 10px 24px -10px rgba(224, 122, 0, 0.65);
    color: #FFF8EC;
  }}
  .label {{
    font-size: 10px; font-weight: 800; letter-spacing: .09em;
    text-transform: uppercase; opacity: .92; margin-bottom: 5px;
  }}
  .text {{ font-size: 13px; line-height: 1.45; }}
  a {{ color: #FFFFFF; font-weight: 700; text-decoration: underline; text-underline-offset: 2px; }}
  .footer {{
    margin-top: 9px; padding-top: 7px;
    border-top: 1px solid rgba(255, 255, 255, 0.25);
    font-size: 10px; opacity: .8;
  }}
  .footer a {{ font-weight: 600; text-decoration: none; }}
  .footer a:hover {{ text-decoration: underline; }}
</style></head>
<body>
  <div class="card">
    <div class="label">{label_html}</div>
    <div class="text">{text_html} <a href="{url_attr}" target="_blank" rel="noopener">{cta_html}</a></div>
    <div class="footer">Ads by <a href="https://getlulu.dev/ads" target="_blank" rel="noopener">Lulu Ads</a></div>
  </div>
<script>
  // MCP Apps handshake: the host keeps the iframe reserved-but-hidden until
  // it receives ui/notifications/initialized (modelcontextprotocol/ext-apps#671).
  // Sent on load plus a short fallback timer so a missed load event can't
  // deadlock the widget into permanently-hidden.
  (function () {{
    var sent = false;
    function notifyInitialized() {{
      if (sent) return;
      sent = true;
      window.parent.postMessage({{ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {{}} }}, "*");
      var h = document.body.scrollHeight;
      if (h) {{
        window.parent.postMessage(
          {{ jsonrpc: "2.0", method: "ui/notifications/size-changed", params: {{ width: 400, height: h }} }},
          "*"
        );
      }}
    }}
    window.addEventListener("load", notifyInitialized);
    setTimeout(notifyInitialized, 300);
  }})();
</script>
</body></html>"""


def register_sponsored_widget(
    mcp,
    *,
    endpoint_url: str,
    text: str,
    url: str,
    label: str = "Sponsored",
    cta: str = "Learn more →",
    resource_uri: str = _DEFAULT_RESOURCE_URI,
    accent: str = _ACCENT,
    accent_light: str = _ACCENT_LIGHT,
    accent_dark: str = _ACCENT_DARK,
    visibility: list | None = None,
):
    """Registers a rendered MCP Apps UI sponsored-card resource on a
    FastMCP server instance and returns the AppConfig to attach to
    whichever tool(s) should carry it::

        app_config = register_sponsored_widget(mcp, endpoint_url=..., text=..., url=...)

        @mcp.tool(app=app_config)
        def my_tool(...): ...

    Requires fastmcp to be installed (not a hard dependency of this
    package — only of this module, same pattern as middleware.py).
    """
    from fastmcp.apps.config import AppConfig

    domain = claude_apps_domain(endpoint_url)
    widget_html = sponsored_widget_html(
        text=text, url=url, label=label, cta=cta,
        accent=accent, accent_light=accent_light, accent_dark=accent_dark,
    )

    @mcp.resource(
        resource_uri,
        name="sponsored_card",
        mime_type="text/html;profile=mcp-app",
        app=AppConfig(domain=domain),
    )
    def _sponsored_card_resource() -> str:
        return widget_html

    return AppConfig(resource_uri=resource_uri, visibility=visibility or ["model"])
