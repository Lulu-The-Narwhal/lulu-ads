"""Lulu Ads client.

Hard guarantees, enforced here rather than documented:
- never raises: any failure returns None
- hard wall-clock timeout, enforced once as a single outer deadline (never
  also passed to httpx's own per-request timeout -- doing both used to race,
  see _resolve_timeout_ms and sponsored_slot's _fetch): default 800ms, or
  3000ms when the call implies server-side classification. A tool call can
  never hang on ads, in both the async (sponsored_slot) and sync
  (sponsored_slot_sync) variants.
- any call made more than _KEEPALIVE_EXPIRY_S since this client's last real
  success (or one that has never succeeded at all) gets _COLD_START_TIMEOUT_MS
  of headroom instead of the tight steady-state budget, unless the caller
  passed an explicit timeout_ms (a deliberate choice, never second-guessed).
  This re-arms on every idle gap, not just once per process -- see
  _COLD_START_TIMEOUT_MS's comment for why a one-time "ever succeeded" latch
  was tried first and found wrong.
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
# 155-215ms once the connection is warm, and 800ms was sized off that.
# Real production evidence (2026-07-26, via demo-flights-mcp's debug
# logging) contradicted the 155-215ms figure directly: calls this client
# itself judged NOT cold (a real success inside the keepalive window)
# still measured 796-802ms twice -- i.e. right at the 800ms line, not
# comfortably under it, and one of those two timed out. Whatever the
# 155-215ms number was measured against, it isn't representative of this
# path's real p95 today. Raised to keep real margin over what's actually
# been observed warm, not what was once assumed warm.
#
# _CLASSIFY_TIMEOUT_MS covers matching + network + the server-side Gemini
# hop, and only applies when that hop is actually going to run.
_FAST_TIMEOUT_MS = 1500
_CLASSIFY_TIMEOUT_MS = 3000
_DEFAULT_CACHE_TTL_MS = 45_000

# Root cause of a real, reproducible 0% delivery rate discovered 2026-07-26:
# remote MCP hosts that reconnect per message (confirmed live: Claude.ai's
# connector opens a brand-new MCP session -- new TCP/TLS, new
# clientInfo/initialize handshake, different source IP -- for every single
# chat message, not once per conversation) mean the underlying HTTP
# connection this SDK's persistent client pools is cold far more often than
# "once at process start": httpx's own default keepalive_expiry (5s) closes
# the pooled connection after any 5s idle gap, and a REAL chat conversation
# almost always leaves more than 5s between messages -- a human reading and
# typing. So a fresh TCP+TLS handshake is the common case, not a one-time
# startup cost, and it recurs for the life of the process.
#
# First attempt at a fix (shipped, then found wrong on inspection): latch a
# per-client "have I ever succeeded" boolean and give ONLY the
# genuinely-first-ever call the larger budget. That's wrong the moment
# coldness recurs: call 1 succeeds with the extra headroom, the latch flips
# permanently true, and call 2 -- arriving after the very same kind of >5s
# idle gap -- gets throttled back to the tight 800ms budget while facing an
# equally cold connection. A retry-on-timeout was tried next, but that's
# also wrong: it can't distinguish "connection was actually cold" from "the
# connection was fine, ads-server is just slow right now" (both look
# identical from the outside as a wall-clock timeout), so it silently
# breaks the deliberate guarantee that a slow-but-connected ads-server can
# never stall the caller past the steady-state budget (confirmed by this
# SDK's own test suite: a warmed client hitting a merely-slow response must
# still fail at the tight budget, not get rescued).
#
# Real fix: don't latch a boolean, don't retry -- track WHEN this client
# last actually succeeded (a real sponsored_slot response, or a warm_up()/
# async_warm_up() health check), and re-arm the larger budget any time
# that's more than _KEEPALIVE_EXPIRY_S ago (or never happened at all). This
# directly mirrors reality: a connection idle longer than the pool's own
# keepalive window is genuinely likely to need a fresh handshake, no matter
# how many prior calls succeeded; a connection used seconds ago is not, and
# a slow response on it is almost certainly the server, not the socket --
# exactly the case that must still fail fast.
_COLD_START_TIMEOUT_MS = 3000

# httpx's own default (5.0s) evicts a pooled connection after any 5s idle
# gap -- far shorter than the real gap between two chat messages, which is
# why nearly every real call was hitting a cold connection (see
# _COLD_START_TIMEOUT_MS's comment). Raised generously so the common case
# of normal human-paced chat gaps reuses a warm connection and stays fast;
# also used as the "was my last success recent enough to trust this
# connection is still warm" window for the cold-start check above -- the
# two should track each other, since one is about what the pool actually
# does and the other is this client's own best guess about it.
_KEEPALIVE_EXPIRY_S = 90.0


def _resolve_timeout_ms(context: dict | None, timeout_ms: int | None) -> int:
    if timeout_ms is not None:
        return timeout_ms
    if isinstance(context, dict) and context.get("prompt") and not context.get("category"):
        return _CLASSIFY_TIMEOUT_MS
    return _FAST_TIMEOUT_MS


# Temporary diagnostic aid for confirming the retry-on-timeout fix live
# (LULU_ADS_DEBUG=1) -- prints to stderr so it lands in the host process's
# own logs (e.g. `kubectl logs`) without needing a logging framework
# dependency. Never raises; never touches request/response bodies (no PII,
# no ad copy) beyond timing and outcome. Safe to delete once the fix is
# confirmed working against a real remote MCP host and this stops being
# actively debugged.
_DEBUG = os.environ.get("LULU_ADS_DEBUG") == "1"


def _debug_log(msg: str) -> None:
    if _DEBUG:
        try:
            import sys

            print(f"[lulu_ads] {msg}", file=sys.stderr, flush=True)
        except Exception:
            pass

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
    if json_body.get("imp_url"):
        # Rendered-impression beacon: widget frames fire this as a 1px img
        # the moment the sponsored strip actually shows, so "rendered" is
        # counted separately from "returned" (CPM only ever pays rendered).
        result["imp_url"] = str(json_body["imp_url"])
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
        # monotonic timestamp of this client's last real success (a
        # sponsored_slot response or a warm_up()/async_warm_up() health
        # check) -- None until the first one. Read by sponsored_slot/
        # sponsored_slot_sync to decide whether THIS call should get
        # _COLD_START_TIMEOUT_MS's headroom. See _COLD_START_TIMEOUT_MS's
        # module comment for why this replaced a one-time "ever succeeded"
        # boolean.
        self._last_success_at: float | None = None

    def _is_cold(self) -> bool:
        return self._last_success_at is None or (time.monotonic() - self._last_success_at) > _KEEPALIVE_EXPIRY_S

    def _ensure_sync_client(self) -> httpx.Client:
        with self._client_lock:
            if self._sync_client is None or self._sync_client_transport is not self._transport:
                if self._sync_client is not None:
                    try:
                        self._sync_client.close()
                    except Exception:
                        pass
                self._sync_client = httpx.Client(
                    timeout=5.0,
                    transport=self._transport,
                    limits=httpx.Limits(keepalive_expiry=_KEEPALIVE_EXPIRY_S),
                )
                self._sync_client_transport = self._transport
            return self._sync_client

    def _ensure_async_client(self) -> httpx.AsyncClient:
        with self._client_lock:
            if self._async_client is None or self._async_client_transport is not self._transport:
                self._async_client = httpx.AsyncClient(
                    timeout=5.0,
                    transport=self._transport,
                    limits=httpx.Limits(keepalive_expiry=_KEEPALIVE_EXPIRY_S),
                )
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
            resp = client.get(f"{self._base_url}/health", timeout=5.0)
            if resp.status_code == 200:
                self._last_success_at = time.monotonic()
        except Exception:
            pass
        try:
            # Local import, not module-level: lulu_ads/__init__.py imports
            # LuluAds from this file, so importing __version__ from
            # lulu_ads at module load time here would be circular. Safe at
            # call time -- warm_up() can't run before the package has
            # finished importing.
            from lulu_ads import __version__ as _sdk_version

            client = self._ensure_sync_client()
            client.post(
                f"{self._base_url}/telemetry/init",
                headers={"x-api-key": self._api_key or ""},
                json={"sdk_version": _sdk_version, "language": "python"},
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
            resp = await client.get(f"{self._base_url}/health", timeout=5.0)
            if resp.status_code == 200:
                self._last_success_at = time.monotonic()
        except Exception:
            pass
        try:
            from lulu_ads import __version__ as _sdk_version

            client = self._ensure_async_client()
            await client.post(
                f"{self._base_url}/telemetry/init",
                headers={"x-api-key": self._api_key or ""},
                json={"sdk_version": _sdk_version, "language": "python"},
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
        # Only when the caller didn't pass their own timeout_ms (an explicit
        # value is a deliberate choice, never second-guessed): if this
        # client's last real success was too long ago to trust the pooled
        # connection is still warm (or there's never been one), give this
        # call real cold-connection headroom instead of the tight budget.
        # See _COLD_START_TIMEOUT_MS's module comment for why this is a
        # per-call, time-windowed check rather than a one-time latch or a
        # retry.
        was_cold = timeout_ms is None and self._is_cold()
        if was_cold:
            effective_timeout_ms = max(effective_timeout_ms, _COLD_START_TIMEOUT_MS)

        async def _fetch(client: httpx.AsyncClient):
            # Do NOT also pass timeout_ms here: httpx's own per-request
            # timeout and asyncio.wait_for's outer deadline below used to
            # both fire at the same instant. Whichever won the race cancelled
            # the request mid-flight, which corrupts the pooled connection
            # and forces the NEXT call to reconnect cold too. One deadline,
            # enforced once, outside: httpx keeps its own generous
            # client-level default (5.0s) as an inert backstop.
            r = await client.post(**self._request_args(cleaned))
            if r.status_code != 200:
                return None
            return _parse(r.status_code, r.json() if r.content else None)

        t0 = time.monotonic()
        try:
            client = self._ensure_async_client()
            result = await asyncio.wait_for(_fetch(client), timeout=effective_timeout_ms / 1000)
            _debug_log(
                f"async cold={was_cold} timeout_ms={effective_timeout_ms} "
                f"elapsed_ms={(time.monotonic() - t0) * 1000:.0f} ok={result is not None}"
            )
        except Exception as exc:
            result = None
            _debug_log(
                f"async cold={was_cold} timeout_ms={effective_timeout_ms} "
                f"elapsed_ms={(time.monotonic() - t0) * 1000:.0f} error={type(exc).__name__}"
            )

        if result is not None:
            self._last_success_at = time.monotonic()
            if cache_key is not None:
                self._cache[cache_key] = (result, time.time() + self._cache_ttl_ms / 1000)
        return result

    async def confirm_cli_delivery(self, imp_url: str) -> None:
        """Fire-and-forget delivery beacon for CLI/text clients.

        The normal `imp_url` beacon is a 1x1 pixel a rendering client fetches
        itself the moment it displays the sponsored strip -- CLI/terminal
        clients have no rendering engine to do that, so without this the
        card is appended to content[] but NEVER logged as delivered anywhere.
        This calls the same beacon URL from inside our own server instead,
        tagged `src=cli_server` so ads-server logs it as the distinct,
        weaker "cli_card_delivered" signal (proves the card left our server
        in the response, never that a human saw it) -- NOT
        "impression_rendered", and never counted toward CPM billing.

        Best-effort only: a short timeout and a swallow-everything except
        on failure, exactly like the rest of this client's fail-open
        philosophy -- this must never delay or break the tool call it rides
        alongside, since by the time this runs the tool response has
        already been built and is on its way out.
        """
        if not imp_url:
            return
        sep = "&" if "?" in imp_url else "?"
        try:
            client = self._ensure_async_client()
            await client.get(f"{imp_url}{sep}src=cli_server", timeout=2.0)
        except Exception:
            pass

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
        # See sponsored_slot's identical comment above.
        was_cold = timeout_ms is None and self._is_cold()
        if was_cold:
            effective_timeout_ms = max(effective_timeout_ms, _COLD_START_TIMEOUT_MS)

        def _fetch(client: httpx.Client):
            # Same reasoning as the async path above: one deadline (the
            # future.result() timeout below), not two racing ones.
            r = client.post(**self._request_args(cleaned))
            if r.status_code != 200:
                return None
            return _parse(r.status_code, r.json() if r.content else None)

        t0 = time.monotonic()
        try:
            client = self._ensure_sync_client()
            future = _get_executor().submit(_fetch, client)
            result = future.result(timeout=effective_timeout_ms / 1000)
            _debug_log(
                f"sync cold={was_cold} timeout_ms={effective_timeout_ms} "
                f"elapsed_ms={(time.monotonic() - t0) * 1000:.0f} ok={result is not None}"
            )
        except FutureTimeoutError:
            # Hard wall-clock cap hit. The worker thread is abandoned here — it
            # keeps running and is itself bounded by httpx's per-phase timeout,
            # but its result is never observed. Acceptable: we never block the
            # caller past the deadline, and the executor's small max_workers
            # bounds how many abandoned requests can pile up.
            result = None
            _debug_log(
                f"sync cold={was_cold} timeout_ms={effective_timeout_ms} "
                f"elapsed_ms={(time.monotonic() - t0) * 1000:.0f} error=FutureTimeoutError"
            )
        except Exception as exc:
            result = None
            _debug_log(
                f"sync cold={was_cold} timeout_ms={effective_timeout_ms} "
                f"elapsed_ms={(time.monotonic() - t0) * 1000:.0f} error={type(exc).__name__}"
            )

        if result is not None:
            self._last_success_at = time.monotonic()
            if cache_key is not None:
                self._cache[cache_key] = (result, time.time() + self._cache_ttl_ms / 1000)
        return result
