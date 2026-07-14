"""Lulu Ads client.

Hard guarantees, enforced here rather than documented:
- never raises: any failure returns None
- hard wall-clock timeout (default 150ms): a tool call can never hang on ads,
  in both the async (sponsored_slot) and sync (sponsored_slot_sync) variants
- the sponsored object always carries label="Sponsored" (FTC disclosure)
- only allowlisted context keys leave the process; no PII fields exist
This SDK ships data, never directives — nothing here instructs a model
to display anything. The host decides.
"""
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import httpx

_ALLOWED_CONTEXT_KEYS = frozenset({"tool", "category", "query", "route", "locale", "country"})
_MAX_VALUE_LEN = 200

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


def _parse(status_code: int, json_body) -> dict | None:
    if status_code != 200 or not isinstance(json_body, dict):
        return None
    text, url = json_body.get("text"), json_body.get("url")
    if not text or not url:
        return None
    return {"label": "Sponsored", "text": str(text), "url": str(url)}


class LuluAds:
    def __init__(
        self,
        publisher_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        # Get from env if not provided
        self._publisher_id = publisher_id or os.environ.get("LULU_ADS_PUBLISHER_ID")
        self._api_key = api_key or os.environ.get("LULU_ADS_API_KEY")

        # Base URL: explicit arg > env var > default fallback
        if base_url is None:
            base_url = os.environ.get("LULU_ADS_BASE_URL", "https://ads.getlulu.dev")

        self._base_url = base_url.rstrip("/")
        self._transport: httpx.BaseTransport | None = None  # test seam

    def _is_inert(self) -> bool:
        """Check if client has minimal creds to make requests."""
        return not self._publisher_id or not self._api_key

    def _request_args(self, context: dict | None) -> dict:
        return {
            "url": f"{self._base_url}/slot",
            "json": {"context": _clean_context(context)},
            "headers": {"x-api-key": self._api_key},
        }

    async def sponsored_slot(self, context: dict | None = None, timeout_ms: int = 150) -> dict | None:
        # If missing creds, return None immediately with no network call
        if self._is_inert():
            return None

        async def _fetch():
            async with httpx.AsyncClient(
                timeout=timeout_ms / 1000, transport=self._transport
            ) as client:
                r = await client.post(**self._request_args(context))
            if r.status_code != 200:
                return None
            return _parse(r.status_code, r.json() if r.content else None)

        try:
            return await asyncio.wait_for(_fetch(), timeout=timeout_ms / 1000)
        except Exception:
            return None

    def sponsored_slot_sync(self, context: dict | None = None, timeout_ms: int = 150) -> dict | None:
        # If missing creds, return None immediately with no network call —
        # before any thread/executor work.
        if self._is_inert():
            return None

        def _fetch():
            with httpx.Client(timeout=timeout_ms / 1000, transport=self._transport) as client:
                r = client.post(**self._request_args(context))
            if r.status_code != 200:
                return None
            return _parse(r.status_code, r.json() if r.content else None)

        try:
            future = _get_executor().submit(_fetch)
            return future.result(timeout=timeout_ms / 1000)
        except FutureTimeoutError:
            # Hard wall-clock cap hit. The worker thread is abandoned here — it
            # keeps running and is itself bounded by httpx's per-phase timeout,
            # but its result is never observed. Acceptable: we never block the
            # caller past the deadline, and the executor's small max_workers
            # bounds how many abandoned requests can pile up.
            return None
        except Exception:
            return None
