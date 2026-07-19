import hashlib

from fastmcp import Client, FastMCP

from lulu_ads.widget import (
    claude_apps_domain,
    register_sponsored_widget,
    sponsored_widget_html,
)


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
    assert 'class="card"' in html
    assert "linear-gradient" in html


def test_widget_html_default_label_is_sponsored():
    html = sponsored_widget_html(text="deal", url="https://x.com")
    assert ">Sponsored<" in html


def test_widget_html_always_carries_lulu_ads_attribution():
    # Not a parameter — every publisher's card carries this, same as
    # "Ads by Google": the network brand compounds across publishers only
    # if it's consistent, not opt-in.
    html = sponsored_widget_html(text="deal", url="https://x.com")
    assert "Ads by" in html
    assert 'href="https://getlulu.dev/ads"' in html


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
        assert ">Ad<" in c.text
