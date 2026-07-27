import httpx
import pytest
from fastmcp import FastMCP

from lulu_ads.enable import enable_lulu_ads
from lulu_ads import widget as widget_mod

GOOD = {"label": "Sponsored", "text": "Lulu Ads", "url": "https://ads.getlulu.dev/c/x"}
ENDPOINT = "https://my-server.example.com/mcp"


def make_server(**kwargs) -> FastMCP:
    mcp = FastMCP(name="test-server")
    enable_lulu_ads(
        mcp,
        endpoint_url=ENDPOINT,
        publisher_id="pub_1",
        api_key="lk_x",
        auto_warm_up=False,
        **kwargs,
    )
    return mcp


async def _get_tool_meta(mcp: FastMCP, name: str) -> dict:
    tool = await mcp.get_tool(name)
    return tool.meta or {}


async def test_bare_decorator_gets_widget_config():
    mcp = make_server()

    @mcp.tool
    def search() -> dict:
        return {"flights": []}

    meta = await _get_tool_meta(mcp, "search")
    assert meta.get("ui", {}).get("resourceUri") == "ui://lulu-ads/sponsored.html"


async def test_parenthesized_decorator_gets_widget_config():
    mcp = make_server()

    @mcp.tool(annotations={"readOnlyHint": True})
    def search() -> dict:
        return {"flights": []}

    meta = await _get_tool_meta(mcp, "search")
    assert meta.get("ui", {}).get("resourceUri") == "ui://lulu-ads/sponsored.html"


async def test_explicit_name_kwarg_gets_widget_config():
    mcp = make_server()

    @mcp.tool(name="search_flights")
    def search() -> dict:
        return {"flights": []}

    meta = await _get_tool_meta(mcp, "search_flights")
    assert meta.get("ui", {}).get("resourceUri") == "ui://lulu-ads/sponsored.html"


async def test_excluded_tool_gets_no_widget_config():
    mcp = make_server(exclude_tools=("private_tool",))

    @mcp.tool
    def private_tool() -> dict:
        return {"secret": True}

    meta = await _get_tool_meta(mcp, "private_tool")
    assert "ui" not in meta


async def test_explicit_app_is_never_overridden():
    from fastmcp.apps.config import AppConfig

    mcp = make_server()
    custom = AppConfig(resource_uri="ui://custom/widget.html", visibility=["model"])

    @mcp.tool(app=custom)
    def search() -> dict:
        return {"flights": []}

    meta = await _get_tool_meta(mcp, "search")
    assert meta.get("ui", {}).get("resourceUri") == "ui://custom/widget.html"


async def test_data_and_widget_both_apply_end_to_end():
    from fastmcp import Client

    mcp = make_server()

    @mcp.tool
    def search() -> dict:
        return {"flights": [{"price": 520}]}

    # Attach the ads transport after enable_lulu_ads constructs its own
    # LuluAdsMiddleware -- same seam pattern as test_middleware.py's
    # make_middleware, reached via the middleware FastMCP just registered.
    ads_middleware = [m for m in mcp.middleware if hasattr(m, "_ads")][0]
    ads_middleware._ads._transport = httpx.MockTransport(lambda r: httpx.Response(200, json=GOOD))

    async with Client(mcp) as client:
        result = await client.call_tool("search", {})
    assert result.structured_content.get("sponsored") == GOOD
    meta = await _get_tool_meta(mcp, "search")
    assert meta.get("ui", {}).get("resourceUri") == "ui://lulu-ads/sponsored.html"


def test_resource_registered_with_claude_domain():
    mcp = make_server()
    domain = widget_mod.claude_apps_domain(ENDPOINT)
    assert domain.endswith(".claudemcpcontent.com")
