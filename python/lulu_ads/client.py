"""Lulu Ads client.

Hard guarantees, enforced here rather than documented:
- never raises: any failure returns None
- hard wall-clock timeout, enforced once as a single outer deadline (never
  also passed to httpx's own per-request timeout -- doing both used to race,
  see _resolve_timeout_ms and sponsored_slot's _fetch): default 800ms, or
  3000ms when the call implies server-side classification. A tool call can
  never hang on ads, in both the async (sponsored_slot) and sync
  (sponsored_slot_sync) variants.
- the sponsored object always carries label="Sponsored" (FTC disclosure)
- only allowlisted context keys leave the process; no PII fields exist
This SDK ships data, never directives — nothing here instructs a model
to display anything. The host decides.
"""
import asyncio
import hashlib
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import httpx

_ALLOWED_CONTEXT_KEYS = frozenset({"tool", "category", "query", "route", "locale", "country", "prompt"})
_MAX_VALUE_LEN = 200
# ads-server only classifies server-side (a real Gemini call on its own 2.0s
# internal budget, see ads-server/app/classify.py) when "category" is absent
# AND "prompt" is present -- an explicit category always short-circuits
# classification. So the wire-level default is conditional on which path a
# given call actually takes, rather than one flat number sized for the
# slowest case: a category-only or context-free call never touches Gemini
# server-side and shouldn't eat a 3s ceiling just because *some* calls do.
#
# _FAST_TIMEOUT_MS covers matching + network only. 150ms was already broken
# for a cold connection alone (measured 2.46s cold vs ~150ms warm against
# ads-server in production); load testing separately measured a steady
# 155-215ms once the connection is warm. 800ms clears a cold connection
# with real margin while staying tight enough that a slow ads-server can't
# visibly stall the caller's own tool call.
#
# _CLASSIFY_TIMEOUT_MS covers matching + network + the server-side Gemini
# hop, and only applies when that hop is actually going to run.
_FAST_TIMEOUT_MS = 800
_CLASSIFY_TIMEOUT_MS = 3000
_DEFAULT_CACHE_TTL_MS = 45_000


def _resolve_timeout_ms(context: dict | None, timeout_ms: int | None) -> int:
    if timeout_ms is not None:
        return timeout_ms
    if isinstance(context, dict) and context.get("prompt") and not context.get("category"):
        return _CLASSIFY_TIMEOUT_MS
    return _FAST_TIMEOUT_MS

# Lazily-created, module-level executor for sponsored_slot_sync. httpx.Client's
# `timeout=` is per-phase (connect/read/write/pool), not a total wall-clock cap,
# and MockTransport ignores it entirely — so we can't rely on it alone to bound
# a call. Running the request in a worker thread lets us enforce a real
# wall-clock deadline via future.result(timeout=...). If the deadline is hit we
# return None immediately; the abandoned thread keeps running in the
# background and will itself terminate once httpx's per-phase timeout fires
# (or the request completes) — its result is simply discarded. Small pool size
# because this is a fire-and-forget sidecar call, not a general-purpose pool.
_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="lulu-ads-sync")
    return _executor


def _clean_context(context: dict | None) -> dict:
    if not isinstance(context, dict):
        return {}
    return {
        k: str(v)[:_MAX_VALUE_LEN]
        for k, v in context.items()
        if k in _ALLOWED_CONTEXT_KEYS and v is not None
    }


def _cache_key(cleaned_context: dict) -> str | None:
    # Category is the stable, low-cardinality identity when explicit.
    # Otherwise, when only a raw prompt is given (the path that triggers
    # ads-server's own server-side Gemini classification, currently the
    # slowest at up to 3000ms), key on a hash of the prompt text so a
    # repeated identical prompt within the TTL skips the classification
    # cost too, not just the network hop. With neither, there's no stable
    # identity to key on without over-broadening the cache (e.g. keying on
    # `tool` alone would return the same ad to every call for that tool
    # regardless of category) -- so no caching happens in that case.
    category = cleaned_context.get("category")
    if category:
        return f"cat:{category}"
    prompt = cleaned_context.get("prompt")
    if prompt:
        return f"prompt:{hashlib.sha256(prompt.encode()).hexdigest()[:16]}"
    return None


def format_suffix(sponsored: dict | None) -> str:
    """For runtimes that OWN the final response surface (chat bots,
    WhatsApp/Telegram agents, self-hosted assistants). The HARNESS appends
    this to the model's output as deterministic code, after generation —
    never as a model instruction. Returns "" for None or a malformed dict
    so callers can always safely concatenate.
    """
    if not isinstance(sponsored, dict):
        return ""
    text, url = sponsored.get("text"), sponsored.get("url")
    if not text or not url:
        return ""
    return f"\n\n— Sponsored: {text} → {url}"


def _parse(status_code: int, json_body) -> dict | None:
    if status_code != 200 or not isinstance(json_body, dict):
        return None
    text, url = json_body.get("text"), json_body.get("url")
    if not text or not url:
        return None
    result = {"label": "Sponsored", "text": str(text), "url": str(url)}
    if json_body.get("logo_url"):
        result["logo_url"] = str(json_body["logo_url"])
    return result


class LuluAds:
    def __init__(
        self,
        publisher_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        cache_ttl_ms: int = _DEFAULT_CACHE_TTL_MS,
    ):
        # Get from env if not provided
        self._publisher_id = publisher_id or os.environ.get("LULU_ADS_PUBLISHER_ID")
        self._api_key = api_key or os.environ.get("LULU_ADS_API_KEY")

        # Base URL: explicit arg > env var > default fallback
        if base_url is None:
            base_url = os.environ.get("LULU_ADS_BASE_URL", "https://ads.getlulu.dev")

        self._base_url = base_url.rstrip("/")
        self._transport: httpx.BaseTransport | None = None  # test seam
        # Persistent clients, created lazily on first use. Constructing an
        # httpx client builds an SSL context (CA-bundle load) which can cost
        # hundreds of ms on CPU-constrained containers — more than a typical
        # slot budget. Paying that once and reusing connections (keep-alive)
        # is the only way small timeout_ms values are meetable in production.
        # If a cold first call exceeds its budget it still returns None, but
        # the abandoned worker finishes construction and caches the client,
        # so every later call runs warm.
        self._sync_client: httpx.Client | None = None
        self._sync_client_transport: httpx.BaseTransport | None = None
        self._async_client: httpx.AsyncClient | None = None
        self._async_client_transport: httpx.BaseTransport | None = None
        self._client_lock = threading.Lock()
        self._cache_ttl_ms = cache_ttl_ms
        self._cache: dict[str, tuple[dict, float]] = {}

    def _ensure_sync_client(self) -> httpx.Client:
        with self._client_lock:
            if self._sync_client is None or self._sync_client_transport is not self._transport:
                if self._sync_client is not None:
                    try:
                        self._sync_client.close()
                    except Exception:
                        pass
                self._sync_client = httpx.Client(timeout=5.0, transport=self._transport)
                self._sync_client_transport = self._transport
            return self._sync_client

    def _ensure_async_client(self) -> httpx.AsyncClient:
        with self._client_lock:
            if self._async_client is None or self._async_client_transport is not self._transport:
                self._async_client = httpx.AsyncClient(timeout=5.0, transport=self._transport)
                self._async_client_transport = self._transport
            return self._async_client

    def _is_inert(self) -> bool:
        """Check if client has minimal creds to make requests."""
        return not self._publisher_id or not self._api_key

    def warm_up(self) -> None:
        """Best-effort: pings ads-server's /health to pre-establish a warm
        TLS connection before any real sponsored_slot call happens, and
        separately reports this publisher's integration as alive via
        POST /telemetry/init (fills the admin dashboard's "installed, not
        yet serving" gap -- see lulu-platform's
        2026-07-24-lulu-ads-sdk-install-tracking-design.md). Not called
        automatically -- firing a real network request as a side effect of
        __init__ is surprising and untestable (a test setting ._transport
        right after construction, the normal pattern in this SDK's own
        test suite, would otherwise race a background thread already using
        the real network). Call this once yourself, in a background
        thread, at your own process startup:

            client = LuluAds(...)
            threading.Thread(target=client.warm_up, daemon=True).start()

        A slot request is often the first outbound call an integrator's
        process makes; the first request on a cold connection can take
        seconds (see _DEFAULT_TIMEOUT_MS's docstring). Never raises.
        """
        try:
            client = self._ensure_sync_client()
            client.get(f"{self._base_url}/health", timeout=5.0)
        except Exception:
            pass
        try:
            client = self._ensure_sync_client()
            client.post(
                f"{self._base_url}/telemetry/init",
                headers={"x-api-key": self._api_key or ""},
                timeout=5.0,
            )
        except Exception:
            pass

    async def async_warm_up(self) -> None:
        """Async counterpart to warm_up() -- pre-establishes a warm
        connection for the ASYNC client (sponsored_slot's pool), which
        warm_up() cannot touch: httpx.AsyncClient binds to whichever event
        loop first uses it, so constructing/warming it from a background
        thread's own throwaway loop and reusing it later on the real
        server's loop raises "Event loop is closed" (verified live).
        Callers must await this from the SAME event loop that will later
        call sponsored_slot() -- in practice, from a real in-loop
        lifecycle hook (FastMCP's on_initialize, LangChain's
        abefore_agent), never from a background thread. Also reports this
        publisher's integration as alive via POST /telemetry/init, same as
        warm_up(). Never raises.
        """
        try:
            client = self._ensure_async_client()
            await client.get(f"{self._base_url}/health", timeout=5.0)
        except Exception:
            pass
        try:
            client = self._ensure_async_client()
            await client.post(
                f"{self._base_url}/telemetry/init",
                headers={"x-api-key": self._api_key or ""},
                timeout=5.0,
            )
        except Exception:
            pass

    def _request_args(self, cleaned_context: dict) -> dict:
        return {
            "url": f"{self._base_url}/slot",
            "json": {"context": cleaned_context},
            "headers": {"x-api-key": self._api_key},
        }

    async def sponsored_slot(
        self, context: dict | None = None, timeout_ms: int | None = None, enabled: bool = True
    ) -> dict | None:
        # `enabled` is the ads on/off switch for integrators running tiered
        # pricing (e.g. a paid tier that's ad-free, a free/discounted tier
        # that carries ads) -- pass enabled=False and this returns
        # immediately with no network call, same as missing credentials.
        # The caller's own subscription/tier check decides the value; nothing
        # here needs to know about pricing tiers.
        if not enabled:
            return None
        # If missing creds, return None immediately with no network call
        if self._is_inert():
            return None

        cleaned = _clean_context(context)
        cache_key = _cache_key(cleaned)
        if cache_key is not None:
            cached = self._cache.get(cache_key)
            if cached is not None and cached[1] > time.time():
                return cached[0]

        effective_timeout_ms = _resolve_timeout_ms(context, timeout_ms)

        async def _fetch():
            client = self._ensure_async_client()
            # Do NOT also pass timeout_ms here: httpx's own per-request
            # timeout and asyncio.wait_for's outer deadline below used to
            # both fire at the same instant. Whichever won the race cancelled
            # the request mid-flight, which corrupts the pooled connection
            # and forces the NEXT call to reconnect cold too — a
            # self-sustaining failure loop that never actually warms up.
            # One deadline, enforced once, outside: httpx keeps its own
            # generous client-level default (5.0s) as an inert backstop.
            r = await client.post(**self._request_args(cleaned))
            if r.status_code != 200:
                return None
            return _parse(r.status_code, r.json() if r.content else None)

        try:
            result = await asyncio.wait_for(_fetch(), timeout=effective_timeout_ms / 1000)
        except Exception:
            result = None

        if result is not None and cache_key is not None:
            self._cache[cache_key] = (result, time.time() + self._cache_ttl_ms / 1000)
        return result

    def sponsored_slot_sync(
        self, context: dict | None = None, timeout_ms: int | None = None, enabled: bool = True
    ) -> dict | None:
        # See sponsored_slot's docstring for what `enabled` is for.
        if not enabled:
            return None
        # If missing creds, return None immediately with no network call —
        # before any thread/executor work.
        if self._is_inert():
            return None

        cleaned = _clean_context(context)
        cache_key = _cache_key(cleaned)
        if cache_key is not None:
            cached = self._cache.get(cache_key)
            if cached is not None and cached[1] > time.time():
                return cached[0]

        effective_timeout_ms = _resolve_timeout_ms(context, timeout_ms)

        def _fetch():
            client = self._ensure_sync_client()
            # Same reasoning as the async path above: one deadline (the
            # future.result() timeout below), not two racing ones.
            r = client.post(**self._request_args(cleaned))
            if r.status_code != 200:
                return None
            return _parse(r.status_code, r.json() if r.content else None)

        try:
            future = _get_executor().submit(_fetch)
            result = future.result(timeout=effective_timeout_ms / 1000)
        except FutureTimeoutError:
            # Hard wall-clock cap hit. The worker thread is abandoned here — it
            # keeps running and is itself bounded by httpx's per-phase timeout,
            # but its result is never observed. Acceptable: we never block the
            # caller past the deadline, and the executor's small max_workers
            # bounds how many abandoned requests can pile up.
            result = None
        except Exception:
            result = None

        if result is not None and cache_key is not None:
            self._cache[cache_key] = (result, time.time() + self._cache_ttl_ms / 1000)
        return result
