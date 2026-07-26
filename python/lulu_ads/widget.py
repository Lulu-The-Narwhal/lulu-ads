"""MCP Apps UI widget helper for FastMCP servers.

Turns the plain `sponsored` data field into an actual rendered card in
hosts that support the MCP Apps extension (io.modelcontextprotocol/ui),
instead of relying on the model's own judgment to format raw JSON nicely.
The plain field always stays too — every host that doesn't support MCP
Apps yet gets the harmless data fallback; this is additive, not a
replacement. Port of js/src/widget.ts — keep both in sync.

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
to. `resource_uri` itself is still registered once, statically, at
registration time -- but the compiled widget bundle now *listens* for the
live `ui/notifications/tool-result` message the MCP Apps host sends on
every tool call (a fresh iframe per call is already how the protocol
works; nothing server-side had to change) and swaps its content to that
call's real `structuredContent.sponsored` data. `text`/`url`/`logo_data_uri`
passed here become that starting "house ad" content baked into the bundle
at render time -- shown only until/unless a live `tool-result` ever
arrives in a given host (a host that doesn't push it at all would keep
showing this baked content indefinitely, same as the old fully-static
behavior); `label`/`cta`/`accent*` additionally become the defaults the
live path falls back to for fields the wire payload doesn't carry (`cta`,
never; `label`, when omitted) and the static per-integrator brand theme
respectively.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging

from lulu_ads._generated_widget_bundle import WIDGET_BUNDLE_HTML

_log = logging.getLogger("lulu_ads.widget")

_OPTS_PLACEHOLDER = "__LULU_ADS_OPTS__"


def _escape_html(s: str) -> str:
    """Mirrors widget.ts's `escapeHtml` byte-for-byte -- deliberately not
    `html.escape()`, which escapes `'` as the numeric-hex `&#x27;` instead
    of TS's decimal `&#39;`. Both decode identically in any browser, but
    the whole point of this port is the *rendered output* staying
    byte-identical between languages, not just browser-equivalent.
    """
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

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
    gradient card with a disclosed label, live-swappable per tool call. The
    markup/CSS/JS themselves come from the compiled `js/widget-src/`
    React/shadcn build (`_generated_widget_bundle.py` -- a single
    self-contained HTML document, everything inlined, no external
    requests, kept byte-identical to the TypeScript side's
    `generatedWidgetBundle.ts` by `scripts/sync-widget-bundle.sh`). This
    function's job is narrower than it used to be: apply the same defaults
    the old hand-written template applied, then substitute the result --
    as an HTML-attribute-escaped JSON blob, so a malicious `text`/`url`
    still can't break out of the markup (mirrors `widget.ts`'s
    `sponsoredWidgetHtml()` and the widget bundle's `mcpBridge.ts`'s
    `readInitialOptions`, which reads this back via `getAttribute`, never
    `innerHTML`) -- into the bundle's `__LULU_ADS_OPTS__` placeholder.

    `logo_data_uri` must already be a `data:` URI (see `fetch_logo_data_uri`
    / `register_sponsored_widget`'s `logo` param) -- a raw `https://` URL
    here would be silently dropped by the widget sandbox's CSP.
    """
    resolved_opts: dict[str, str] = {
        "text": text,
        "url": url,
        "label": label,
        "cta": cta,
    }
    # A key is omitted entirely (not set to None/null) when logo_data_uri
    # is absent -- matches the TS side's JSON.stringify, which drops
    # undefined-valued keys, and the old template's "no <img> element at
    # all when logoDataUri is absent" contract.
    if logo_data_uri is not None:
        resolved_opts["logoDataUri"] = logo_data_uri
    resolved_opts["accent"] = accent
    resolved_opts["accentLight"] = accent_light
    resolved_opts["accentDark"] = accent_dark

    # separators=(",", ":") + ensure_ascii=False mirror JSON.stringify's
    # compact, non-escaping-of-unicode output exactly -- json.dumps's
    # defaults (", "/": " separators, \uXXXX-escaping every non-ASCII
    # char) would otherwise make the injected opts blob diverge from the
    # TS side's byte-for-byte, even though both decode to the same object.
    opts_json = json.dumps(resolved_opts, separators=(",", ":"), ensure_ascii=False)
    opts_attr = _escape_html(opts_json)

    # str.replace already replaces every occurrence by default (unlike
    # JS's default .replace(), which only replaces the first) -- this is
    # already the equivalent of the TS side's explicit .replaceAll(), see
    # widget.ts's comment on why a single-occurrence replace would be
    # unsafe if the placeholder token is ever spelled out again elsewhere
    # in the bundle (e.g. in a comment).
    return WIDGET_BUNDLE_HTML.replace(_OPTS_PLACEHOLDER, opts_attr)


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
