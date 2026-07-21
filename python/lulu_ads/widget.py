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

A third, easy to miss entirely because it fails silently: the widget iframe's
own CSP only allows `img-src 'self' data: <resourceDomains>` (MCP Apps spec).
Point `logo` at your own CDN and nothing in the registration flow tells you
it's blocked -- the card just renders with no logo, forever, in every host,
and there's no console error to find. `logo` is fetched right here at
registration time and inlined as a `data:` URI instead, which `img-src`
always allows -- no `resourceDomains` config, no dependency on your logo's
host staying reachable from the widget's sandbox. This is why `logo` takes a
URL to fetch rather than a URL to embed directly.

Usage:

    from fastmcp import FastMCP
    from lulu_ads.widget import register_sponsored_widget

    mcp = FastMCP("my-server")
    sponsored_app = register_sponsored_widget(
        mcp,
        endpoint_url="https://my-server.example.com/mcp",
        text="Save 15% at checkout",
        url="https://example.com/deal",
        logo="https://example.com/logo.png",  # optional; fetched + inlined
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

import base64
import hashlib
import html as _html
import logging

_log = logging.getLogger("lulu_ads.widget")

_DEFAULT_RESOURCE_URI = "ui://lulu-ads/sponsored.html"

# Keeps the inlined data: URI (and the resource payload every client
# downloads) small -- this renders at 28x28 in the card, never a full-size
# asset. Raise only if you know your host's resource-size limits.
_MAX_LOGO_BYTES = 200_000
_LOGO_FETCH_TIMEOUT_S = 3.0
_ALLOWED_LOGO_CONTENT_TYPES = {
    "image/png", "image/jpeg", "image/jpg", "image/svg+xml", "image/webp", "image/gif",
}

# Test seam: set to an httpx.MockTransport in tests instead of hitting the
# network. None (the default) means fetch_logo_data_uri uses a real
# httpx.Client with no transport override.
_transport = None


def fetch_logo_data_uri(logo_url: str) -> str | None:
    """Downloads `logo_url` and returns it as a `data:` URI, or None on any
    failure (bad status, wrong/missing content-type, oversized, network
    error, timeout) -- a broken logo must never break the widget or the
    server registering it, so this never raises.
    """
    import httpx

    try:
        # Module-level test seam, same pattern as LuluAds._transport in
        # client.py: tests set widget._transport to an httpx.MockTransport
        # instead of hitting the network.
        client_kwargs = {"timeout": _LOGO_FETCH_TIMEOUT_S, "follow_redirects": True}
        if _transport is not None:
            client_kwargs["transport"] = _transport
        with httpx.Client(**client_kwargs) as client:
            resp = client.get(logo_url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if content_type not in _ALLOWED_LOGO_CONTENT_TYPES:
            _log.warning("lulu_ads: skipping logo %s -- unsupported content-type %r", logo_url, content_type)
            return None
        if len(resp.content) > _MAX_LOGO_BYTES:
            _log.warning(
                "lulu_ads: skipping logo %s -- %d bytes exceeds %d byte cap",
                logo_url, len(resp.content), _MAX_LOGO_BYTES,
            )
            return None
        b64 = base64.b64encode(resp.content).decode("ascii")
        return f"data:{content_type};base64,{b64}"
    except Exception as exc:
        _log.warning("lulu_ads: skipping logo %s -- fetch failed: %s", logo_url, exc)
        return None

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
    logo_data_uri: str | None = None,
    accent: str = _ACCENT,
    accent_light: str = _ACCENT_LIGHT,
    accent_dark: str = _ACCENT_DARK,
) -> str:
    """Renders the Lulu Ads sponsored-card widget: a floating, rounded,
    gradient card with a disclosed label. Ships data baked into markup —
    no instruction telling any model or host what to do with it.

    `logo_data_uri` must already be a `data:` URI (see `fetch_logo_data_uri`
    / `register_sponsored_widget`'s `logo` param) -- a raw `https://` URL
    here would be silently dropped by the widget sandbox's CSP.
    """
    text_html = _html.escape(text)
    cta_html = _html.escape(cta)
    url_attr = _html.escape(url, quote=True)
    label_html = _html.escape(label)
    logo_html = (
        f'<img class="logo" src="{_html.escape(logo_data_uri, quote=True)}" alt="">'
        if logo_data_uri else ""
    )
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
  .row {{ display: flex; align-items: flex-start; gap: 10px; }}
  .logo {{
    width: 28px; height: 28px; border-radius: 8px; flex-shrink: 0;
    background: rgba(255, 255, 255, 0.9); object-fit: contain; padding: 2px;
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
    <div class="row">
      {logo_html}
      <div class="text">{text_html} <a href="{url_attr}" target="_blank" rel="noopener">{cta_html}</a></div>
    </div>
    <div class="footer">Powered by <a href="https://getlulu.dev" target="_blank" rel="noopener">Lulu Ads</a></div>
  </div>
<script>
  (function () {{
    // MCP Apps handshake: the host keeps the iframe reserved-but-hidden until
    // it receives ui/notifications/initialized (modelcontextprotocol/ext-apps#671).
    // Sent on load plus a short fallback timer so a missed load event can't
    // deadlock the widget into permanently-hidden.
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

    // Plain <a target="_blank"> clicks get silently swallowed inside the
    // sandboxed MCP Apps iframe (no allow-popups) — right-click "open in
    // new tab" bypasses the iframe's JS entirely, which is why that alone
    // worked. The sanctioned path is ui/open-link, a real JSON-RPC request
    // the host handles outside the sandbox (modelcontextprotocol/ext-apps
    // spec.types.ts: McpUiOpenLinkRequest). href/target stay on the <a> as
    // a harmless fallback for any host that doesn't run this JS.
    document.querySelectorAll("a[href]").forEach(function (link) {{
      link.addEventListener("click", function (e) {{
        e.preventDefault();
        window.parent.postMessage(
          {{ jsonrpc: "2.0", id: "open-link-" + Date.now(), method: "ui/open-link", params: {{ url: link.href }} }},
          "*"
        );
      }});
    }});
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
    logo: str | None = None,
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

    `logo`, if given, is a URL to fetch a brand mark from -- it is
    downloaded once, here, at registration time, and inlined into the
    widget as a `data:` URI (see the module docstring for why a raw remote
    URL would silently never render). A fetch failure just means no logo
    in the card, never a registration error.

    Requires fastmcp to be installed (not a hard dependency of this
    package — only of this module, same pattern as middleware.py).
    """
    from fastmcp.apps.config import AppConfig

    domain = claude_apps_domain(endpoint_url)
    logo_data_uri = fetch_logo_data_uri(logo) if logo else None
    widget_html = sponsored_widget_html(
        text=text, url=url, label=label, cta=cta, logo_data_uri=logo_data_uri,
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
