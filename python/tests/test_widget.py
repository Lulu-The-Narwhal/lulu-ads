import hashlib
import json
import re

import httpx
from fastmcp import Client, FastMCP

import lulu_ads.widget as widget
from lulu_ads.widget import (
    claude_apps_domain,
    fetch_logo_data_uri,
    register_sponsored_widget,
    sponsored_widget_html,
)


def _extract_injected_opts(html: str) -> dict:
    """Pulls the per-call options blob back out of a rendered widget HTML
    string -- the compiled React bundle now renders its actual card
    content client-side from this data (see js/widget-src's
    mcpBridge.ts's `readInitialOptions`), so `sponsored_widget_html()`'s
    returned markup no longer contains a literal `<img class="logo">`/
    label/etc. the way the old hand-written template did -- this is the
    equivalent "did the right data make it into the output" check for the
    new mechanism. Mirrors the browser's own HTML-attribute-value
    decoding (never innerHTML/eval), same as the real
    `readInitialOptions` does.
    """
    match = re.search(r'id="lulu-ads-opts"[^>]*\sdata-opts="([^"]*)"', html)
    assert match, "no #lulu-ads-opts data-opts attribute found in rendered widget HTML"
    decoded = (
        match.group(1)
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&amp;", "&")
    )
    return json.loads(decoded)


def test_claude_apps_domain_is_deterministic_and_matches_formula():
    endpoint = "https://dali.getlulu.dev/mcp"
    expected = hashlib.sha256(endpoint.encode()).hexdigest()[:32] + ".claudemcpcontent.com"
    assert claude_apps_domain(endpoint) == expected
    # deterministic — same input, same output, no side effects
    assert claude_apps_domain(endpoint) == claude_apps_domain(endpoint)


def test_claude_apps_domain_differs_per_endpoint():
    a = claude_apps_domain("https://a.example.com/mcp")
    b = claude_apps_domain("https://b.example.com/mcp")
    assert a != b


def test_widget_html_escapes_content_and_has_handshake():
    html = sponsored_widget_html(text='Save <script>alert(1)</script>', url="https://x.com/?a=1&b=2")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "ui/notifications/initialized" in html
    assert "ui/notifications/size-changed" in html


def test_widget_html_always_carries_lulu_ads_attribution():
    # Not a parameter — every publisher's card carries this, same as
    # "Ads by Google": the network brand compounds across publishers only
    # if it's consistent, not opt-in. Baked into the compiled bundle's
    # footer component, so the string literals survive minification
    # verbatim even though the actual `<a href="...">` DOM only exists
    # once React renders client-side (not checkable from a plain string).
    html = sponsored_widget_html(text="deal", url="https://x.com")
    assert "Powered by" in html
    assert "https://getlulu.dev" in html


def test_widget_html_intercepts_clicks_for_ui_open_link():
    # Plain <a target="_blank"> clicks are silently swallowed inside the
    # sandboxed MCP Apps iframe (no allow-popups) — ui/open-link is the
    # sanctioned host-mediated path (modelcontextprotocol/ext-apps
    # spec.types.ts: McpUiOpenLinkRequest). The compiled/minified bundle
    # no longer contains the old hand-written template's literal
    # unminified JS source, so this only checks the mechanism (the
    # ui/open-link postMessage method name) is still wired in, not the
    # exact source text of the handler.
    html = sponsored_widget_html(text="deal", url="https://x.com")
    assert "ui/open-link" in html


def test_widget_html_omits_logo_data_uri_from_injected_opts_when_absent():
    html = sponsored_widget_html(text="deal", url="https://x.com")
    opts = _extract_injected_opts(html)
    assert "logoDataUri" not in opts


def test_widget_html_carries_logo_data_uri_through_to_injected_opts_when_given():
    html = sponsored_widget_html(
        text="deal", url="https://x.com",
        logo_data_uri="data:image/png;base64,aGVsbG8=",
    )
    opts = _extract_injected_opts(html)
    assert opts["logoDataUri"] == "data:image/png;base64,aGVsbG8="


def test_widget_html_applies_built_in_defaults_when_omitted():
    html = sponsored_widget_html(text="deal", url="https://x.com")
    opts = _extract_injected_opts(html)
    assert opts["label"] == "Sponsored"
    assert opts["cta"] == "Learn more →"
    assert opts["accent"] == "#E07A00"
    assert opts["accentLight"] == "#F5A623"
    assert opts["accentDark"] == "#B55E00"


def test_widget_html_carries_every_option_through_when_all_are_overridden():
    html = sponsored_widget_html(
        text="Save big",
        url="https://example.com/deal",
        label="Ad",
        cta="Shop now",
        logo_data_uri="data:image/png;base64,aGVsbG8=",
        accent="#111111",
        accent_light="#222222",
        accent_dark="#000000",
    )
    opts = _extract_injected_opts(html)
    assert opts == {
        "text": "Save big",
        "url": "https://example.com/deal",
        "label": "Ad",
        "cta": "Shop now",
        "template": "card",
        "logoDataUri": "data:image/png;base64,aGVsbG8=",
        "accent": "#111111",
        "accentLight": "#222222",
        "accentDark": "#000000",
    }


def test_widget_html_injected_opts_attr_is_byte_identical_to_the_ts_side():
    # This is the check that actually discriminates: decoding-then-
    # comparing (as every other test here does) can't see whitespace,
    # separator, or escaping differences -- both `{"a": 1}` and `{"a":1}`
    # decode to the same object. The TS side's JSON.stringify + escapeHtml
    # produce a *compact* JSON blob (no space after `,`/`:`), non-ASCII
    # characters left literal (not \uXXXX-escaped), and `'` escaped as the
    # decimal `&#39;` (not html.escape's hex `&#x27;`) -- this asserts the
    # raw injected attribute string matches that exact form, hand-computed
    # here the way JSON.stringify(opts) + widget.ts's escapeHtml would
    # produce it, apostrophe and non-ASCII included.
    html = sponsored_widget_html(text="Mom's deal →", url="https://x.com")
    match = re.search(r'id="lulu-ads-opts"[^>]*\sdata-opts="([^"]*)"', html)
    assert match
    expected_json = (
        '{"text":"Mom\'s deal →","url":"https://x.com",'
        '"label":"Sponsored","cta":"Learn more →","template":"card",'
        '"accent":"#E07A00","accentLight":"#F5A623","accentDark":"#B55E00"}'
    )
    expected_attr = (
        expected_json.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
    assert match.group(1) == expected_attr


def test_widget_html_is_genuinely_self_contained():
    # No external <script src>/<link href> references -- the compiled
    # bundle must be fully self-contained (same guard export-bundle.mjs
    # and scripts/sync_widget_bundle.py both enforce at build/sync time).
    html = sponsored_widget_html(text="deal", url="https://x.com")
    assert not re.search(r"<script[^>]*\ssrc=", html)
    assert not re.search(r"<link[^>]*\shref=", html)
    assert re.search(r'<script type="module"[^>]*>[\s\S]+</script>', html)


def test_fetch_logo_data_uri_inlines_a_small_allowed_image(monkeypatch):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG-fake-bytes")

    monkeypatch.setattr(widget, "_transport", httpx.MockTransport(handler))
    result = fetch_logo_data_uri("https://example.com/logo.png")
    assert result is not None
    assert result.startswith("data:image/png;base64,")


def test_fetch_logo_data_uri_rejects_disallowed_content_type(monkeypatch):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html></html>")

    monkeypatch.setattr(widget, "_transport", httpx.MockTransport(handler))
    assert fetch_logo_data_uri("https://example.com/not-an-image") is None


def test_fetch_logo_data_uri_rejects_oversized_image(monkeypatch):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"x" * (widget._MAX_LOGO_BYTES + 1))

    monkeypatch.setattr(widget, "_transport", httpx.MockTransport(handler))
    assert fetch_logo_data_uri("https://example.com/huge.png") is None


def test_fetch_logo_data_uri_rejects_non_200(monkeypatch):
    def handler(request):
        return httpx.Response(404)

    monkeypatch.setattr(widget, "_transport", httpx.MockTransport(handler))
    assert fetch_logo_data_uri("https://example.com/missing.png") is None


def test_fetch_logo_data_uri_never_raises_on_network_error(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    monkeypatch.setattr(widget, "_transport", httpx.MockTransport(handler))
    assert fetch_logo_data_uri("https://example.com/logo.png") is None


async def test_register_sponsored_widget_inlines_logo(monkeypatch):
    def handler(request):
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG-fake-bytes")

    monkeypatch.setattr(widget, "_transport", httpx.MockTransport(handler))
    mcp = FastMCP(name="test-server-logo")
    app_config = register_sponsored_widget(
        mcp,
        endpoint_url="https://test-server-logo.example.com/mcp",
        text="deal",
        url="https://example.com",
        logo="https://example.com/logo.png",
    )
    async with Client(mcp) as client:
        content = await client.read_resource("ui://lulu-ads/sponsored.html")
        [c] = content
        opts = _extract_injected_opts(c.text)
        assert opts["logoDataUri"].startswith("data:image/png;base64,")


async def test_register_sponsored_widget_bad_logo_still_registers(monkeypatch):
    def handler(request):
        return httpx.Response(500)

    monkeypatch.setattr(widget, "_transport", httpx.MockTransport(handler))
    mcp = FastMCP(name="test-server-bad-logo")
    app_config = register_sponsored_widget(
        mcp,
        endpoint_url="https://test-server-bad-logo.example.com/mcp",
        text="deal",
        url="https://example.com",
        logo="https://example.com/broken.png",
    )
    async with Client(mcp) as client:
        content = await client.read_resource("ui://lulu-ads/sponsored.html")
        [c] = content
        opts = _extract_injected_opts(c.text)
        assert "logoDataUri" not in opts
        assert opts["text"] == "deal"


async def test_register_sponsored_widget_wires_resource_and_returns_app_config():
    mcp = FastMCP(name="test-server")
    app_config = register_sponsored_widget(
        mcp,
        endpoint_url="https://test-server.example.com/mcp",
        text="Save 15% at checkout",
        url="https://example.com/deal",
    )
    assert app_config.resource_uri == "ui://lulu-ads/sponsored.html"
    assert app_config.visibility == ["model"]

    @mcp.tool(app=app_config)
    def search() -> dict:
        return {"results": []}

    async with Client(mcp) as client:
        resources = await client.list_resources()
        uris = [str(r.uri) for r in resources]
        assert "ui://lulu-ads/sponsored.html" in uris

        [target] = [r for r in resources if str(r.uri) == "ui://lulu-ads/sponsored.html"]
        expected_domain = claude_apps_domain("https://test-server.example.com/mcp")
        assert target.meta["ui"]["domain"] == expected_domain

        content = await client.read_resource("ui://lulu-ads/sponsored.html")
        [c] = content
        assert "Save 15% at checkout" in c.text
        assert "https://example.com/deal" in c.text

        tools = await client.list_tools()
        [search_tool] = [t for t in tools if t.name == "search"]
        assert search_tool.meta["ui"]["resourceUri"] == "ui://lulu-ads/sponsored.html"


async def test_register_sponsored_widget_custom_resource_uri_and_label():
    mcp = FastMCP(name="test-server-2")
    app_config = register_sponsored_widget(
        mcp,
        endpoint_url="https://test-server-2.example.com/mcp",
        text="deal",
        url="https://example.com",
        label="Ad",
        resource_uri="ui://custom/card.html",
    )
    assert app_config.resource_uri == "ui://custom/card.html"

    async with Client(mcp) as client:
        content = await client.read_resource("ui://custom/card.html")
        [c] = content
        opts = _extract_injected_opts(c.text)
        assert opts["label"] == "Ad"


# ── template= (LUL-46 registry infra) ───────────────────────────────────

def test_widget_html_defaults_to_card_template():
    html = sponsored_widget_html(text="deal", url="https://x.com")
    assert _extract_injected_opts(html)["template"] == "card"


def test_widget_html_rejects_unknown_template():
    try:
        sponsored_widget_html(text="deal", url="https://x.com", template="banner")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unknown template 'banner'" in str(exc)
        assert "card" in str(exc)


def test_register_sponsored_widget_rejects_unknown_template_before_any_network_call():
    mcp = FastMCP(name="test-server-bad-template")
    calls = []
    import lulu_ads.widget as widget_module
    widget_module._transport = __import__("httpx").MockTransport(lambda r: calls.append(1) or __import__("httpx").Response(200))
    try:
        try:
            register_sponsored_widget(
                mcp,
                endpoint_url="https://test-server-bad-template.example.com/mcp",
                text="deal",
                url="https://example.com",
                logo="https://example.com/logo.png",
                template="does-not-exist",
            )
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "unknown template 'does-not-exist'" in str(exc)
        # The logo fetch never happened -- validation ran first.
        assert calls == []
    finally:
        widget_module._transport = None


async def test_register_sponsored_widget_carries_template_through_to_resource():
    mcp = FastMCP(name="test-server-template")
    register_sponsored_widget(
        mcp,
        endpoint_url="https://test-server-template.example.com/mcp",
        text="deal",
        url="https://example.com",
        template="card",
    )
    async with Client(mcp) as client:
        content = await client.read_resource("ui://lulu-ads/sponsored.html")
        [c] = content
        assert _extract_injected_opts(c.text)["template"] == "card"
