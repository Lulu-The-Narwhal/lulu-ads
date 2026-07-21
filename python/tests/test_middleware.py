import asyncio
import threading

import httpx
import mcp.types as mt
import pytest
from fastmcp import Client, FastMCP

from lulu_ads import LuluAds
from lulu_ads.middleware import LuluAdsMiddleware

GOOD = {"label": "Sponsored", "text": "Lulu Ads", "url": "https://ads.getlulu.dev/c/x"}
CLAUDE_CODE = mt.Implementation(name="claude-code", version="2.1.212")


def make_middleware(handler) -> LuluAdsMiddleware:
    # auto_warm_up=False: a background thread already headed for the real
    # network would otherwise race ._transport being set to the mock right
    # after construction (exactly the hazard documented in middleware.py
    # and warm_up()'s own docstring).
    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
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

    mw = LuluAdsMiddleware(
        publisher_id="pub_1", api_key="lk_x", exclude_tools=("private_tool",), auto_warm_up=False
    )
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
    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x", cli_text_mode=True, auto_warm_up=False)
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
    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x", cli_text_mode=True, auto_warm_up=False)
    mw._ads._transport = httpx.MockTransport(lambda r: httpx.Response(200, json=GOOD))
    async with Client(make_server(mw), client_info=CLAUDE_CODE) as client:
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert result.structured_content.get("sponsored") == GOOD
    card_texts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    assert any("via Lulu Ads" in t for t in card_texts)


async def test_cli_text_mode_leaves_non_cli_clients_untouched():
    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x", cli_text_mode=True, auto_warm_up=False)
    mw._ads._transport = httpx.MockTransport(lambda r: httpx.Response(200, json=GOOD))
    async with Client(make_server(mw)) as client:  # not claude-code
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert result.structured_content.get("sponsored") == GOOD


def test_auto_warm_up_fires_by_default(monkeypatch):
    # Regression: the first real tool call on a freshly started server
    # measured 804ms against the 800ms fast-path default -- a genuinely
    # cold connection sits right at that ceiling, not comfortably under
    # it. Zero-config warm-up on construction is what closes that gap.
    fired = threading.Event()
    monkeypatch.setattr(LuluAds, "warm_up", lambda self: fired.set())
    LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x")
    assert fired.wait(timeout=1.0), "warm_up() was not called from a background thread"


def test_auto_warm_up_false_never_fires(monkeypatch):
    fired = threading.Event()
    monkeypatch.setattr(LuluAds, "warm_up", lambda self: fired.set())
    LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
    assert not fired.wait(timeout=0.2)


def test_default_timeout_is_not_a_hardcoded_number():
    # Regression: this used to default to 300, hardcoded here rather than
    # deferring to client.py's own conditional 800ms/3000ms default. Found
    # live (not by any test in this file) against a real cold ads-server
    # call that a real round-trip sits close enough to 300ms that it has
    # no margin -- every test below uses an instant MockTransport, which
    # is exactly why a real-latency timeout bug like this can ship
    # unnoticed through a fully green mocked suite.
    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
    assert mw._timeout_ms is None


async def test_slow_but_realistic_response_still_fills():
    # 500ms is slower than any mocked test elsewhere in this file, but
    # still well inside a real cold-connection round trip -- the exact
    # zone where the old hardcoded 300ms default would have timed out and
    # silently dropped a real, fillable ad. With timeout_ms left at its
    # default (None -> client.py's conditional default), this must fill.
    async def slow(request):
        await asyncio.sleep(0.5)
        return httpx.Response(200, json=GOOD)

    mw = make_middleware(slow)
    async with Client(make_server(mw)) as client:
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert result.structured_content.get("sponsored") == GOOD


async def test_no_args_no_env_is_inert(monkeypatch):
    monkeypatch.delenv("LULU_ADS_PUBLISHER_ID", raising=False)
    monkeypatch.delenv("LULU_ADS_API_KEY", raising=False)
    monkeypatch.delenv("LULU_ADS_BASE_URL", raising=False)

    mw = LuluAdsMiddleware(auto_warm_up=False)
    async with Client(make_server(mw)) as client:
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert result.structured_content == {"flights": [{"price": 520}]}
    assert "sponsored" not in result.structured_content
