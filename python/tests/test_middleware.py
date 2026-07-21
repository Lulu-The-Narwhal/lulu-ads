import httpx
import mcp.types as mt
import pytest
from fastmcp import Client, FastMCP

from lulu_ads import LuluAds
from lulu_ads.middleware import LuluAdsMiddleware

GOOD = {"label": "Sponsored", "text": "Lulu Ads", "url": "https://ads.getlulu.dev/c/x"}
CLAUDE_CODE = mt.Implementation(name="claude-code", version="2.1.212")


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

    @mcp.tool
    def untyped_tool():  # no return annotation -> no outputSchema
        return "Found 3 flights TLV -> BKK."

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


async def test_cli_client_gets_card_appended_to_content():
    mw = make_middleware(lambda r: httpx.Response(200, json=GOOD))
    async with Client(make_server(mw), client_info=CLAUDE_CODE) as client:
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    card_texts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    assert any("Sponsored" in t and "via Lulu Ads" in t for t in card_texts)
    # default cli_text_mode=False -- structuredContent untouched, sponsored still added
    assert result.structured_content.get("sponsored") == GOOD


async def test_non_cli_client_gets_no_card():
    mw = make_middleware(lambda r: httpx.Response(200, json=GOOD))
    async with Client(make_server(mw)) as client:  # default client_info, not claude-code
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    card_texts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    assert not any("via Lulu Ads" in t for t in card_texts)
    assert result.structured_content.get("sponsored") == GOOD


async def test_cli_text_mode_strips_structured_content_for_schemaless_tools():
    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x", cli_text_mode=True)
    mw._ads._transport = httpx.MockTransport(lambda r: httpx.Response(200, json=GOOD))
    async with Client(make_server(mw), client_info=CLAUDE_CODE) as client:
        result = await client.call_tool("untyped_tool", {})
    assert result.structured_content is None
    card_texts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    assert any("via Lulu Ads" in t for t in card_texts)


async def test_cli_text_mode_never_strips_structured_content_when_tool_has_output_schema():
    # search_flights returns `-> dict`, which FastMCP auto-generates an
    # outputSchema for. Stripping structuredContent there would make
    # schema-validating clients reject the whole tool call -- confirmed via
    # fastmcp.exceptions.ToolError before this guard existed. cli_text_mode
    # must never do that, even when explicitly enabled.
    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x", cli_text_mode=True)
    mw._ads._transport = httpx.MockTransport(lambda r: httpx.Response(200, json=GOOD))
    async with Client(make_server(mw), client_info=CLAUDE_CODE) as client:
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert result.structured_content.get("sponsored") == GOOD
    card_texts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    assert any("via Lulu Ads" in t for t in card_texts)


async def test_cli_text_mode_leaves_non_cli_clients_untouched():
    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x", cli_text_mode=True)
    mw._ads._transport = httpx.MockTransport(lambda r: httpx.Response(200, json=GOOD))
    async with Client(make_server(mw)) as client:  # not claude-code
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert result.structured_content.get("sponsored") == GOOD


async def test_no_args_no_env_is_inert(monkeypatch):
    monkeypatch.delenv("LULU_ADS_PUBLISHER_ID", raising=False)
    monkeypatch.delenv("LULU_ADS_API_KEY", raising=False)
    monkeypatch.delenv("LULU_ADS_BASE_URL", raising=False)

    mw = LuluAdsMiddleware()
    async with Client(make_server(mw)) as client:
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert result.structured_content == {"flights": [{"price": 520}]}
    assert "sponsored" not in result.structured_content
