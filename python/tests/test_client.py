import asyncio
import time

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


def test_sync_timeout_returns_none():
    """sponsored_slot_sync must enforce a real wall-clock cap, not a per-phase
    httpx timeout — MockTransport ignores httpx's timeout= entirely, so this
    only passes if the sync path has its own hard deadline (thread + future)."""
    def slow(request):
        time.sleep(1.0)
        return httpx.Response(200, json=GOOD)
    ads = make_client(slow)

    start = time.monotonic()
    out = ads.sponsored_slot_sync(context={"tool": "x"}, timeout_ms=50)
    elapsed = time.monotonic() - start

    assert out is None
    assert elapsed < 0.6


async def test_no_args_no_env_returns_none(monkeypatch):
    """When no args and no env vars, client is inert: returns None, transport never called."""
    monkeypatch.delenv("LULU_ADS_PUBLISHER_ID", raising=False)
    monkeypatch.delenv("LULU_ADS_API_KEY", raising=False)
    monkeypatch.delenv("LULU_ADS_BASE_URL", raising=False)

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


def test_sync_client_is_persistent_across_calls():
    """Regression: constructing httpx.Client per call costs an SSL-context
    build (~hundreds of ms on constrained containers) — enough to blow the
    entire slot budget deterministically. The client must be created once
    and reused."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"text": "t", "url": "u"})

    ads = LuluAds("pub_x", "key_x")
    ads._transport = httpx.MockTransport(handler)
    assert ads.sponsored_slot_sync(timeout_ms=1000) is not None
    first = ads._sync_client
    assert first is not None
    assert ads.sponsored_slot_sync(timeout_ms=1000) is not None
    assert ads._sync_client is first
    assert calls["n"] == 2


def test_sync_client_rebuilt_when_transport_changes():
    def ok(request):
        return httpx.Response(200, json={"text": "t", "url": "u"})

    def fail(request):
        return httpx.Response(500)

    ads = LuluAds("pub_x", "key_x")
    ads._transport = httpx.MockTransport(ok)
    assert ads.sponsored_slot_sync(timeout_ms=1000) is not None
    ads._transport = httpx.MockTransport(fail)
    assert ads.sponsored_slot_sync(timeout_ms=1000) is None


async def test_prompt_passes_through_context_allowlist():
    def handler(request):
        import json
        body = json.loads(request.content)
        assert body["context"] == {"prompt": "best flights to paris"}
        return httpx.Response(200, json=GOOD)
    ads = make_client(handler)
    out = await ads.sponsored_slot(context={"prompt": "best flights to paris"})
    assert out == GOOD


async def test_logo_url_passed_through_when_present():
    with_logo = dict(GOOD, logo_url="https://example.com/logo.png")
    ads = make_client(lambda r: httpx.Response(200, json=with_logo))
    out = await ads.sponsored_slot(context={"tool": "x"})
    assert out["logo_url"] == "https://example.com/logo.png"


async def test_logo_url_absent_when_not_in_response():
    ads = make_client(lambda r: httpx.Response(200, json=GOOD))
    out = await ads.sponsored_slot(context={"tool": "x"})
    assert "logo_url" not in out


def test_classify_timeout_has_real_headroom_over_server_side_classify_budget():
    # ads-server's own classify_prompt budget is 2.0s (app/classify.py) --
    # the classify-path default must clear that with room for matching +
    # network, not just be "not 150ms".
    from lulu_ads.client import _CLASSIFY_TIMEOUT_MS
    assert _CLASSIFY_TIMEOUT_MS >= 2500


async def test_fast_default_times_out_without_prompt():
    # No prompt, no explicit timeout_ms -> the fast default applies, which
    # must NOT have classify-sized headroom, or a stalled ads-server could
    # visibly stall the caller's own tool call on the common category-only path.
    async def slow(request):
        await asyncio.sleep(1.0)
        return httpx.Response(200, json=GOOD)
    ads = make_client(slow)
    assert await ads.sponsored_slot(context={"tool": "x"}) is None


async def test_classify_default_survives_prompt_without_category():
    # Prompt present, category absent -> ads-server may run its own Gemini
    # classify call, so the default must have real headroom over that.
    async def slow(request):
        await asyncio.sleep(1.0)
        return httpx.Response(200, json=GOOD)
    ads = make_client(slow)
    out = await ads.sponsored_slot(context={"prompt": "best flights to paris"})
    assert out == GOOD


async def test_fast_default_applies_even_with_prompt_when_category_explicit():
    # Explicit category always short-circuits server-side classification,
    # so the fast default applies even though a prompt is also present.
    async def slow(request):
        await asyncio.sleep(1.0)
        return httpx.Response(200, json=GOOD)
    ads = make_client(slow)
    out = await ads.sponsored_slot(context={"category": "travel.flights", "prompt": "best flights to paris"})
    assert out is None


def test_warm_up_hits_health_endpoint_and_never_raises():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="ok")

    ads = LuluAds("pub_x", "key_x", base_url="https://ads.example.com")
    ads._transport = httpx.MockTransport(handler)
    ads.warm_up()
    assert calls == ["https://ads.example.com/health"]


def test_sync_fast_default_times_out_without_prompt():
    def slow(request):
        time.sleep(1.0)
        return httpx.Response(200, json=GOOD)
    ads = make_client(slow)
    start = time.monotonic()
    out = ads.sponsored_slot_sync(context={"tool": "x"})
    elapsed = time.monotonic() - start
    assert out is None
    assert elapsed < 1.0  # fast default (800ms) must fire well before the 1.0s handler completes


def test_warm_up_never_raises_on_failure():
    ads = LuluAds("pub_x", "key_x")
    ads._transport = httpx.MockTransport(lambda r: httpx.Response(500))
    ads.warm_up()  # must not raise


async def test_async_warm_up_hits_health_endpoint_and_never_raises():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="ok")

    ads = LuluAds("pub_x", "key_x", base_url="https://ads.example.com")
    ads._transport = httpx.MockTransport(handler)
    await ads.async_warm_up()
    assert calls == ["https://ads.example.com/health"]


async def test_async_warm_up_never_raises_on_failure():
    ads = LuluAds("pub_x", "key_x")
    ads._transport = httpx.MockTransport(lambda r: httpx.Response(500))
    await ads.async_warm_up()  # must not raise


# ── enabled=False (tiered-pricing ads on/off switch) ────────────────────

async def test_enabled_false_skips_with_no_network_call():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=GOOD)

    ads = make_client(handler)
    out = await ads.sponsored_slot(context={"tool": "x"}, enabled=False)
    assert out is None
    assert calls == []


async def test_enabled_true_is_the_default():
    ads = make_client(lambda r: httpx.Response(200, json=GOOD))
    assert await ads.sponsored_slot(context={"tool": "x"}) == GOOD


def test_sync_enabled_false_skips_with_no_network_call():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=GOOD)

    ads = make_client(handler)
    out = ads.sponsored_slot_sync(context={"tool": "x"}, enabled=False)
    assert out is None
    assert calls == []


# ── short-TTL cache ─────────────────────────────────────────────────────


async def test_cache_hit_within_ttl_skips_network():
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=GOOD)
    ads = make_client(handler)
    first = await ads.sponsored_slot(context={"category": "travel.flights"})
    second = await ads.sponsored_slot(context={"category": "travel.flights"})
    assert first == GOOD
    assert second == GOOD
    assert len(calls) == 1  # second call served from cache, no network


async def test_cache_expires_after_ttl():
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=GOOD)
    ads = LuluAds(publisher_id="pub_1", api_key="lk_x", cache_ttl_ms=10)
    ads._transport = httpx.MockTransport(handler)
    await ads.sponsored_slot(context={"category": "travel.flights"})
    time.sleep(0.05)
    await ads.sponsored_slot(context={"category": "travel.flights"})
    assert len(calls) == 2  # cache expired, second call re-fetched


async def test_failure_is_never_cached():
    responses = iter([httpx.Response(500), httpx.Response(200, json=GOOD)])
    def handler(request):
        return next(responses)
    ads = make_client(handler)
    first = await ads.sponsored_slot(context={"category": "travel.flights"})
    second = await ads.sponsored_slot(context={"category": "travel.flights"})
    assert first is None
    assert second == GOOD  # not suppressed by a cached failure


async def test_cache_keys_on_prompt_hash_when_no_category():
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=GOOD)
    ads = make_client(handler)
    await ads.sponsored_slot(context={"prompt": "best flights to paris"})
    await ads.sponsored_slot(context={"prompt": "best flights to paris"})
    await ads.sponsored_slot(context={"prompt": "a totally different prompt"})
    assert len(calls) == 2  # same prompt cached, different prompt re-fetches


async def test_no_category_or_prompt_never_caches():
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=GOOD)
    ads = make_client(handler)
    await ads.sponsored_slot(context={"tool": "search_flights"})
    await ads.sponsored_slot(context={"tool": "search_flights"})
    assert len(calls) == 2  # no stable cache key -> always fetches


def test_sync_cache_hit_within_ttl_skips_network():
    calls = []
    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=GOOD)
    ads = make_client(handler)
    first = ads.sponsored_slot_sync(context={"category": "travel.flights"})
    second = ads.sponsored_slot_sync(context={"category": "travel.flights"})
    assert first == GOOD
    assert second == GOOD
    assert len(calls) == 1
