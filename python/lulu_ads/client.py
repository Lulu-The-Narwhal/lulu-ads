"""Lulu Ads client.

Hard guarantees, enforced here rather than documented:
- never raises: any failure returns None
- hard timeout (default 150ms): a tool call can never hang on ads
- the sponsored object always carries label="Sponsored" (FTC disclosure)
- only allowlisted context keys leave the process; no PII fields exist
This SDK ships data, never directives — nothing here instructs a model
to display anything. The host decides.
"""
import asyncio
import os

import httpx

_ALLOWED_CONTEXT_KEYS = frozenset({"tool", "category", "query", "route", "locale", "country"})
_MAX_VALUE_LEN = 200


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
            return _parse(r.status_code, r.json() if r.content else None)

        try:
            return await asyncio.wait_for(_fetch(), timeout=timeout_ms / 1000)
        except Exception:
            return None

    def sponsored_slot_sync(self, context: dict | None = None, timeout_ms: int = 150) -> dict | None:
        # If missing creds, return None immediately with no network call
        if self._is_inert():
            return None

        try:
            with httpx.Client(timeout=timeout_ms / 1000, transport=self._transport) as client:
                r = client.post(**self._request_args(context))
            return _parse(r.status_code, r.json() if r.content else None)
        except Exception:
            return None
