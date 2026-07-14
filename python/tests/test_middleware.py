import httpx
import pytest
from fastmcp import Client, FastMCP

from lulu_ads import LuluAds
from lulu_ads.middleware import LuluAdsMiddleware

GOOD = {"label": "Sponsored", "text": "Lulu Ads", "url": "https://ads.getlulu.dev/c/x"}


def make_middleware(handler) -> LuluAdsMiddleware:
    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x")
    mw._ads._transport = httpx.MockTransport(handler)
    return mw


def make_server(middleware: LuluAdsMiddleware) -> FastMCP:
    mcp = FastMCP(name="test-server")

    @mcp.tool
    def search_flights(origin: str, dest: str) -> dict:
        return {"flights": [{"price": 520}]}

    @mcp.tool
    def private_tool() -> dict:
        return {"secret": True}

    mcp.add_middleware(middleware)
    return mcp


async def test_sponsored_attached_to_dict_results():
    mw = make_middleware(lambda r: httpx.Response(200, json=GOOD))
    async with Client(make_server(mw)) as client:
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert result.structured_content.get("sponsored") == GOOD
    assert result.structured_content["flights"] == [{"price": 520}]


async def test_no_fill_leaves_result_untouched():
    mw = make_middleware(lambda r: httpx.Response(204))
    async with Client(make_server(mw)) as client:
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert "sponsored" not in result.structured_content


async def test_excluded_tool_never_calls_ads():
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(200, json=GOOD)

    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x", exclude_tools=("private_tool",))
    mw._ads._transport = httpx.MockTransport(handler)
    async with Client(make_server(mw)) as client:
        result = await client.call_tool("private_tool", {})
    assert "sponsored" not in result.structured_content
    assert calls == []


async def test_ads_backend_down_is_invisible():
    def boom(r):
        raise httpx.ConnectError("refused")

    mw = make_middleware(boom)
    async with Client(make_server(mw)) as client:
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert result.structured_content["flights"] == [{"price": 520}]
    assert "sponsored" not in result.structured_content


async def test_no_args_no_env_is_inert(monkeypatch):
    monkeypatch.delenv("LULU_ADS_PUBLISHER_ID", raising=False)
    monkeypatch.delenv("LULU_ADS_API_KEY", raising=False)
    monkeypatch.delenv("LULU_ADS_BASE_URL", raising=False)

    mw = LuluAdsMiddleware()
    async with Client(make_server(mw)) as client:
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert result.structured_content == {"flights": [{"price": 520}]}
    assert "sponsored" not in result.structured_content
