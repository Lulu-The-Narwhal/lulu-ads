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


def make_warmed_client(handler) -> LuluAds:
    """A client with a real success just now -- steady-state (within the
    keepalive window), not the genuinely-first-request-ever or
    idle-too-long case _COLD_START_TIMEOUT_MS exists for."""
    ads = make_client(handler)
    ads._last_success_at = time.monotonic()
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
    # visibly stall the caller's own tool call on the common category-only
    # path. This is the STEADY-STATE guarantee -- a warmed client, i.e. one
    # that's already had a real success -- not the genuinely-first-request
    # case, which _COLD_START_TIMEOUT_MS deliberately exempts (see below).
    async def slow(request):
        await asyncio.sleep(2.0)
        return httpx.Response(200, json=GOOD)
    ads = make_warmed_client(slow)
    assert await ads.sponsored_slot(context={"tool": "x"}) is None


async def test_classify_default_survives_prompt_without_category():
    # Prompt present, category absent -> ads-server may run its own Gemini
    # classify call, so the default must have real headroom over that.
    async def slow(request):
        await asyncio.sleep(1.0)
        return httpx.Response(200, json=GOOD)
    ads = make_warmed_client(slow)
    out = await ads.sponsored_slot(context={"prompt": "best flights to paris"})
    assert out == GOOD


async def test_first_request_ever_gets_cold_start_headroom():
    # Root cause of a real 0% delivery rate against remote MCP hosts that
    # reconnect per message (Claude.ai's connector, confirmed live): every
    # call looked like the first-ever request, and 800ms isn't enough for a
    # real cold TLS handshake (measured 2.46s in production). A fresh
    # client's first call must survive something slower than the fast
    # default but comfortably under _COLD_START_TIMEOUT_MS.
    async def slow(request):
        await asyncio.sleep(1.5)
        return httpx.Response(200, json=GOOD)
    ads = make_client(slow)
    assert ads._last_success_at is None
    out = await ads.sponsored_slot(context={"tool": "x"})
    assert out == GOOD


async def test_a_call_soon_after_success_does_not_get_cold_start_headroom():
    # The SECOND call, arriving well within the keepalive window of the
    # first success, must revert to the tight steady-state timeout --
    # cold-start headroom re-arms on a real idle gap, it isn't a permanent
    # loosening of the fast path's guarantee.
    async def slow(request):
        await asyncio.sleep(2.0)
        return httpx.Response(200, json=GOOD)
    ads = make_client(slow)
    first = await ads.sponsored_slot(context={"tool": "x"})
    assert first == GOOD
    assert ads._last_success_at is not None
    second = await ads.sponsored_slot(context={"tool": "y"})
    assert second is None


async def test_a_call_long_after_success_gets_cold_start_headroom_again():
    # Idle longer than _KEEPALIVE_EXPIRY_S since the last success -- the
    # pooled connection is genuinely likely to be cold again (or actually
    # evicted by the real pool), so this call should get the same headroom
    # as a genuinely-first-ever call, not the tight budget.
    async def slow(request):
        await asyncio.sleep(1.5)
        return httpx.Response(200, json=GOOD)
    ads = make_client(slow)
    from lulu_ads.client import _KEEPALIVE_EXPIRY_S
    ads._last_success_at = time.monotonic() - (_KEEPALIVE_EXPIRY_S + 1)
    out = await ads.sponsored_slot(context={"tool": "x"})
    assert out == GOOD


async def test_cold_start_headroom_does_not_override_explicit_timeout_ms():
    # An explicit timeout_ms is a deliberate integrator choice and must
    # never be silently overridden, even on a client's genuinely-first call.
    async def slow(request):
        await asyncio.sleep(1.5)
        return httpx.Response(200, json=GOOD)
    ads = make_client(slow)
    assert ads._last_success_at is None
    out = await ads.sponsored_slot(context={"tool": "x"}, timeout_ms=200)
    assert out is None


async def test_warm_up_success_updates_last_success_at():
    # A successful warm_up()/async_warm_up() health check is real evidence
    # the connection is live -- it should count the same as a real
    # sponsored_slot success, so a call right after a completed warm-up
    # correctly gets the tight steady-state timeout instead of needlessly
    # waiting up to _COLD_START_TIMEOUT_MS.
    def handler(request):
        return httpx.Response(200)
    ads = make_client(handler)
    assert ads._last_success_at is None
    ads.warm_up()
    assert ads._last_success_at is not None


async def test_fast_default_applies_even_with_prompt_when_category_explicit():
    # Explicit category always short-circuits server-side classification,
    # so the fast default applies even though a prompt is also present.
    # Steady-state guarantee (see test_fast_default_times_out_without_prompt) --
    # a warmed client, not the exempted first-ever request.
    async def slow(request):
        await asyncio.sleep(2.0)
        return httpx.Response(200, json=GOOD)
    ads = make_warmed_client(slow)
    out = await ads.sponsored_slot(context={"category": "travel.flights", "prompt": "best flights to paris"})
    assert out is None


def test_warm_up_hits_health_and_telemetry_endpoints_and_never_raises():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="ok")

    ads = LuluAds("pub_x", "key_x", base_url="https://ads.example.com")
    ads._transport = httpx.MockTransport(handler)
    ads.warm_up()
    assert calls == ["https://ads.example.com/health", "https://ads.example.com/telemetry/init"]


def test_warm_up_telemetry_call_carries_api_key_header():
    captured = {}

    def handler(request):
        if "/telemetry/init" in str(request.url):
            captured["x-api-key"] = request.headers.get("x-api-key")
        return httpx.Response(200, text="ok")

    ads = LuluAds("pub_x", "key_x", base_url="https://ads.example.com")
    ads._transport = httpx.MockTransport(handler)
    ads.warm_up()
    assert captured["x-api-key"] == "key_x"


def test_warm_up_telemetry_call_reports_sdk_version():
    import json

    from lulu_ads import __version__

    captured = {}

    def handler(request):
        if "/telemetry/init" in str(request.url):
            captured["body"] = json.loads(request.content)
        return httpx.Response(200, text="ok")

    ads = LuluAds("pub_x", "key_x", base_url="https://ads.example.com")
    ads._transport = httpx.MockTransport(handler)
    ads.warm_up()
    assert captured["body"] == {"sdk_version": __version__, "language": "python"}


def test_sync_fast_default_times_out_without_prompt():
    # Steady-state guarantee -- a warmed client, not the exempted
    # first-ever request (see test_first_request_ever_gets_cold_start_headroom).
    def slow(request):
        time.sleep(2.0)
        return httpx.Response(200, json=GOOD)
    ads = make_warmed_client(slow)
    start = time.monotonic()
    out = ads.sponsored_slot_sync(context={"tool": "x"})
    elapsed = time.monotonic() - start
    assert out is None
    assert elapsed < 2.0  # fast default (1500ms) must fire well before the 2.0s handler completes


def test_warm_up_never_raises_on_failure():
    ads = LuluAds("pub_x", "key_x")
    ads._transport = httpx.MockTransport(lambda r: httpx.Response(500))
    ads.warm_up()  # must not raise


async def test_async_warm_up_hits_health_and_telemetry_endpoints_and_never_raises():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="ok")

    ads = LuluAds("pub_x", "key_x", base_url="https://ads.example.com")
    ads._transport = httpx.MockTransport(handler)
    await ads.async_warm_up()
    assert calls == ["https://ads.example.com/health", "https://ads.example.com/telemetry/init"]


async def test_async_warm_up_telemetry_call_carries_api_key_header():
    captured = {}

    def handler(request):
        if "/telemetry/init" in str(request.url):
            captured["x-api-key"] = request.headers.get("x-api-key")
        return httpx.Response(200, text="ok")

    ads = LuluAds("pub_x", "key_x", base_url="https://ads.example.com")
    ads._transport = httpx.MockTransport(handler)
    await ads.async_warm_up()
    assert captured["x-api-key"] == "key_x"


async def test_async_warm_up_telemetry_call_reports_sdk_version():
    import json

    from lulu_ads import __version__

    captured = {}

    def handler(request):
        if "/telemetry/init" in str(request.url):
            captured["body"] = json.loads(request.content)
        return httpx.Response(200, text="ok")

    ads = LuluAds("pub_x", "key_x", base_url="https://ads.example.com")
    ads._transport = httpx.MockTransport(handler)
    await ads.async_warm_up()
    assert captured["body"] == {"sdk_version": __version__, "language": "python"}


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


# ── confirm_cli_delivery (LUL-62 delivery-confirmed beacon) ─────────────

async def test_confirm_cli_delivery_tags_beacon_with_cli_server_src():
    requests = []
    ads = make_client(lambda r: requests.append(r) or httpx.Response(200))
    await ads.confirm_cli_delivery("https://ads.getlulu.dev/i/tok123")
    assert len(requests) == 1
    assert requests[0].url.params.get("src") == "cli_server"


async def test_confirm_cli_delivery_preserves_existing_query_params():
    requests = []
    ads = make_client(lambda r: requests.append(r) or httpx.Response(200))
    await ads.confirm_cli_delivery("https://ads.getlulu.dev/i/tok123?foo=bar")
    assert requests[0].url.params.get("foo") == "bar"
    assert requests[0].url.params.get("src") == "cli_server"


async def test_confirm_cli_delivery_noop_on_empty_url():
    calls = []
    ads = make_client(lambda r: calls.append(1) or httpx.Response(200))
    await ads.confirm_cli_delivery("")
    assert calls == []


async def test_confirm_cli_delivery_swallows_failures():
    ads = make_client(lambda r: httpx.Response(500))
    await ads.confirm_cli_delivery("https://ads.getlulu.dev/i/tok123")  # must not raise

    def boom(r):
        raise httpx.ConnectError("refused")

    ads2 = make_client(boom)
    await ads2.confirm_cli_delivery("https://ads.getlulu.dev/i/tok123")  # must not raise


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
