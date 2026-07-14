import asyncio

import httpx
import pytest

from lulu_ads import LuluAds

GOOD = {"label": "Sponsored", "text": "El Al TLV→BKK direct, $520", "url": "https://ads.getlulu.dev/c/x"}


def make_client(handler) -> LuluAds:
    ads = LuluAds(publisher_id="pub_1", api_key="lk_x")
    ads._transport = httpx.MockTransport(handler)  # test seam
    return ads


async def test_happy_path():
    def handler(request):
        import json
        body = json.loads(request.content)
        assert request.headers["x-api-key"] == "lk_x"
        assert body["context"] == {"tool": "search_flights"}
        return httpx.Response(200, json=GOOD)
    ads = make_client(handler)
    out = await ads.sponsored_slot(context={"tool": "search_flights"})
    assert out == GOOD


async def test_204_returns_none():
    ads = make_client(lambda r: httpx.Response(204))
    assert await ads.sponsored_slot(context={"tool": "x"}) is None


async def test_500_returns_none():
    ads = make_client(lambda r: httpx.Response(500, text="boom"))
    assert await ads.sponsored_slot(context={"tool": "x"}) is None


async def test_timeout_returns_none():
    async def slow(request):
        await asyncio.sleep(1.0)
        return httpx.Response(200, json=GOOD)
    ads = make_client(slow)
    out = await ads.sponsored_slot(context={"tool": "x"}, timeout_ms=50)
    assert out is None


async def test_network_error_returns_none():
    def boom(request):
        raise httpx.ConnectError("refused")
    ads = make_client(boom)
    assert await ads.sponsored_slot(context={"tool": "x"}) is None


async def test_label_is_forced():
    def handler(request):
        return httpx.Response(200, json={"label": "Ad!!", "text": "t", "url": "https://u"})
    ads = make_client(handler)
    out = await ads.sponsored_slot(context={})
    assert out["label"] == "Sponsored"


async def test_malformed_body_returns_none():
    ads = make_client(lambda r: httpx.Response(200, json={"nope": 1}))
    assert await ads.sponsored_slot(context={}) is None


async def test_context_keys_allowlisted():
    captured = {}
    def handler(request):
        import json
        captured.update(json.loads(request.content)["context"])
        return httpx.Response(204)
    ads = make_client(handler)
    await ads.sponsored_slot(context={"tool": "x", "user_email": "a@b.c", "ssn": "1"})
    assert captured == {"tool": "x"}  # PII-ish keys never leave the process


def test_sync_variant():
    ads = make_client(lambda r: httpx.Response(200, json=GOOD))
    assert ads.sponsored_slot_sync(context={"tool": "x"}) == GOOD


async def test_no_args_no_env_returns_none():
    """When no args and no env vars, client is inert: returns None, transport never called."""
    call_count = []

    def handler(request):
        call_count.append(1)
        return httpx.Response(200, json=GOOD)

    ads = LuluAds()  # no args
    ads._transport = httpx.MockTransport(handler)
    out = await ads.sponsored_slot(context={"tool": "x"})
    assert out is None
    assert len(call_count) == 0  # transport was never called


async def test_env_vars_set(monkeypatch):
    """When env vars are set, client uses them."""
    monkeypatch.setenv("LULU_ADS_PUBLISHER_ID", "pub_env")
    monkeypatch.setenv("LULU_ADS_API_KEY", "lk_env_key")
    monkeypatch.setenv("LULU_ADS_BASE_URL", "https://custom.ads.example.com")

    captured_headers = {}

    def handler(request):
        captured_headers.update(request.headers)
        return httpx.Response(200, json=GOOD)

    ads = LuluAds()  # no args, should use env
    ads._transport = httpx.MockTransport(handler)
    out = await ads.sponsored_slot(context={"tool": "x"})

    assert out == GOOD
    assert captured_headers.get("x-api-key") == "lk_env_key"
