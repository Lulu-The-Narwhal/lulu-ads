import asyncio
import threading

import httpx
import mcp.types as mt
import pytest
from fastmcp import Client, FastMCP

from lulu_ads import LuluAds
from lulu_ads.middleware import LuluAdsMiddleware

GOOD = {"label": "Sponsored", "text": "Lulu Ads", "url": "https://ads.getlulu.dev/c/x"}
GOOD_WITH_IMP = {**GOOD, "imp_url": "https://ads.getlulu.dev/i/tok123"}
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

    OWN_SPONSORED = {"label": "Insurance", "text": "Trip insurance", "url": "https://ads.getlulu.dev/c/y"}

    @mcp.tool
    def preset_sponsored_tool() -> dict:
        # Mirrors demo-flights-mcp's own pattern: the tool picks its own
        # category-specific ad and sets `sponsored` itself, deliberately
        # ahead of the middleware, so the middleware's own generic slot
        # never overwrites it (see the "sponsored" in structured check).
        return {"flights": [{"price": 520}], "sponsored": OWN_SPONSORED}

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


async def test_is_error_result_suppresses_ads_on_success_shaped_host_error():
    # Mirrors a host whose caught/actionable errors come back as normal
    # successful-shaped content instead of a real is_error result.
    mw = LuluAdsMiddleware(
        publisher_id="pub_1",
        api_key="lk_x",
        auto_warm_up=False,
        is_error_result=lambda r: isinstance(r.structured_content, dict)
        and r.structured_content.get("ok") is False,
    )
    mw._ads._transport = httpx.MockTransport(lambda r: httpx.Response(200, json=GOOD))
    mcp = FastMCP(name="test-server")

    @mcp.tool
    def flaky() -> dict:
        return {"ok": False, "reason": "device not found"}

    mcp.add_middleware(mw)
    async with Client(mcp) as client:
        result = await client.call_tool("flaky", {})
    assert "sponsored" not in result.structured_content


async def test_is_error_result_that_raises_fails_open_to_no_ad():
    # Same fail-open contract as every other internal failure in this
    # middleware: a broken classifier means we can't confidently say the
    # result is safe to decorate, so it's left untouched rather than
    # risking an ad landing on an unrecognized error -- not a "show the ad
    # anyway" fallback.
    mw = LuluAdsMiddleware(
        publisher_id="pub_1",
        api_key="lk_x",
        auto_warm_up=False,
        is_error_result=lambda r: 1 / 0,
    )
    mw._ads._transport = httpx.MockTransport(lambda r: httpx.Response(200, json=GOOD))
    async with Client(make_server(mw)) as client:
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert "sponsored" not in result.structured_content
    assert result.structured_content["flights"] == [{"price": 520}]


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


async def test_non_cli_client_content_matches_structured_content():
    # Regression test for a real, live-confirmed bug: FastMCP builds
    # content[] once, from the tool's ORIGINAL return value, before this
    # middleware ever runs. Mutating structured_content alone (the only
    # thing the OTHER tests here checked) left content[] permanently stale
    # -- still the pre-ad JSON. Confirmed against a real MCP client
    # (Claude.ai): the wire response's structuredContent demonstrably had
    # "sponsored", but the client read and reported back from content[],
    # which didn't -- so the ad was fetched successfully and never seen.
    # Every other test in this file asserted structured_content only, which
    # is exactly why this shipped unnoticed. content[] must carry the same
    # data structured_content does, not just a human-readable card (that's
    # the is_cli path, covered separately).
    import json

    mw = make_middleware(lambda r: httpx.Response(200, json=GOOD))
    async with Client(make_server(mw)) as client:  # default client_info, not claude-code
        result = await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    assert len(result.content) == 1
    content_json = json.loads(result.content[0].text)
    assert content_json.get("sponsored") == GOOD
    assert content_json == result.structured_content


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


async def test_cli_client_gets_card_for_tool_preset_sponsored():
    # Regression test for a real, live-confirmed bug: a tool that sets its
    # own `sponsored` field (e.g. demo-flights-mcp's category-specific
    # insurance cross-sell) triggers the "never overwrite" early return --
    # which used to happen BEFORE the CLI-client check, so CLI hosts
    # (Claude Code) got no card at all: no widget surface (rich-UI only)
    # and no text-card safety net either (skipped by the same early
    # return). Net effect: the ad silently never rendered for CLI clients
    # on any tool using this documented self-select pattern.
    calls = []
    mw = make_middleware(lambda r: calls.append(1) or httpx.Response(200, json=GOOD))
    async with Client(make_server(mw), client_info=CLAUDE_CODE) as client:
        result = await client.call_tool("preset_sponsored_tool", {})
    card_texts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    assert any("Insurance" in t and "Trip insurance" in t and "via Lulu Ads" in t for t in card_texts)
    # Never re-fetched or overwritten -- the tool's own choice is final.
    assert calls == []
    assert result.structured_content["sponsored"]["label"] == "Insurance"


async def test_cli_client_fires_delivery_beacon_with_imp_url():
    # LUL-62: CLI clients can't auto-fetch imp_url like a rendering client
    # would, so without a server-side beacon a CLI-delivered card is
    # invisible in ad_events. The middleware must fire it itself, tagged
    # src=cli_server so ads-server logs a distinct "cli_card_delivered"
    # event rather than conflating it with pixel-confirmed impressions.
    from lulu_ads.middleware import _background_tasks

    beacon_requests = []

    def handler(r: httpx.Request):
        if r.method == "GET" and "/i/tok123" in str(r.url):
            beacon_requests.append(r)
            return httpx.Response(200)
        return httpx.Response(200, json=GOOD_WITH_IMP)

    mw = make_middleware(handler)
    async with Client(make_server(mw), client_info=CLAUDE_CODE) as client:
        await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    if _background_tasks:
        await asyncio.gather(*list(_background_tasks))

    assert len(beacon_requests) == 1
    assert beacon_requests[0].url.params.get("src") == "cli_server"


async def test_cli_client_skips_beacon_when_no_imp_url():
    # GOOD (no imp_url) is what ads-server returns when nothing needs
    # delivery confirmation for this slot -- must not synthesize a beacon
    # call out of nothing.
    from lulu_ads.middleware import _background_tasks

    calls = []
    mw = make_middleware(lambda r: calls.append(r) or httpx.Response(200, json=GOOD))
    async with Client(make_server(mw), client_info=CLAUDE_CODE) as client:
        await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    if _background_tasks:
        await asyncio.gather(*list(_background_tasks))

    assert all(r.method != "GET" for r in calls)


async def test_non_cli_client_never_fires_delivery_beacon():
    from lulu_ads.middleware import _background_tasks

    calls = []
    mw = make_middleware(lambda r: calls.append(r) or httpx.Response(200, json=GOOD_WITH_IMP))
    async with Client(make_server(mw)) as client:  # not claude-code
        await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    if _background_tasks:
        await asyncio.gather(*list(_background_tasks))

    assert all(r.method != "GET" for r in calls)


async def test_cli_client_fires_delivery_beacon_for_tool_preset_sponsored():
    # Same beacon must fire on the OTHER is_cli card-append site: a tool
    # that sets its own `sponsored` field (see test_cli_client_gets_card_
    # for_tool_preset_sponsored above) rather than the middleware's own
    # fetched slot.
    from lulu_ads.middleware import _background_tasks

    beacon_requests = []
    OWN_SPONSORED_WITH_IMP = {
        "label": "Insurance", "text": "Trip insurance",
        "url": "https://ads.getlulu.dev/c/y", "imp_url": "https://ads.getlulu.dev/i/tok456",
    }

    def handler(r: httpx.Request):
        if r.method == "GET" and "/i/tok456" in str(r.url):
            beacon_requests.append(r)
        return httpx.Response(200)

    mcp = FastMCP(name="preset-test-server")

    @mcp.tool
    def preset_sponsored_tool() -> dict:
        return {"flights": [{"price": 520}], "sponsored": OWN_SPONSORED_WITH_IMP}

    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
    mw._ads._transport = httpx.MockTransport(handler)
    mcp.add_middleware(mw)

    async with Client(mcp, client_info=CLAUDE_CODE) as client:
        await client.call_tool("preset_sponsored_tool", {})
    if _background_tasks:
        await asyncio.gather(*list(_background_tasks))

    assert len(beacon_requests) == 1
    assert beacon_requests[0].url.params.get("src") == "cli_server"


async def test_non_cli_client_gets_no_card_for_tool_preset_sponsored():
    mw = make_middleware(lambda r: httpx.Response(200, json=GOOD))
    async with Client(make_server(mw)) as client:  # not claude-code
        result = await client.call_tool("preset_sponsored_tool", {})
    card_texts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
    assert not any("via Lulu Ads" in t for t in card_texts)
    assert result.structured_content["sponsored"]["label"] == "Insurance"


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


async def test_async_warm_up_fires_via_on_initialize(monkeypatch):
    # Isolate from the unrelated sync warm_up's background thread (would
    # otherwise also fire and hit the real network in this test).
    monkeypatch.setattr(LuluAds, "warm_up", lambda self: None)
    fired = asyncio.Event()

    async def fake_async_warm_up(self):
        fired.set()

    monkeypatch.setattr(LuluAds, "async_warm_up", fake_async_warm_up)

    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x")
    mw._ads._transport = httpx.MockTransport(lambda r: httpx.Response(204))
    async with Client(make_server(mw)) as client:
        await asyncio.wait_for(fired.wait(), timeout=1.0)


async def test_async_warm_up_fires_only_once(monkeypatch):
    monkeypatch.setattr(LuluAds, "warm_up", lambda self: None)
    call_count = {"n": 0}

    async def fake_async_warm_up(self):
        call_count["n"] += 1

    monkeypatch.setattr(LuluAds, "async_warm_up", fake_async_warm_up)

    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x")
    mw._ads._transport = httpx.MockTransport(lambda r: httpx.Response(204))
    async with Client(make_server(mw)) as client:
        await client.call_tool("search_flights", {"origin": "TLV", "dest": "BKK"})
    await asyncio.sleep(0.05)  # let the fire-and-forget task actually run
    assert call_count["n"] == 1


def test_async_warm_up_never_fires_when_auto_warm_up_false(monkeypatch):
    fired = []

    async def fake_async_warm_up(self):
        fired.append(1)

    monkeypatch.setattr(LuluAds, "async_warm_up", fake_async_warm_up)
    mw = LuluAdsMiddleware(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
    mw._ads._transport = httpx.MockTransport(lambda r: httpx.Response(204))

    async def run():
        async with Client(make_server(mw)):
            pass

    asyncio.run(run())
    assert fired == []
