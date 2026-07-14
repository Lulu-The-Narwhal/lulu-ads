"""One-line monetization for FastMCP servers.

    mcp.add_middleware(LuluAdsMiddleware())

Attaches a labeled `sponsored` data field to tool results. Never a directive,
never on excluded tools, never on existing `sponsored` keys, never on errors,
and never able to break the tool: any ads failure (missing credentials,
network error, timeout, malformed response) leaves the result exactly as the
tool returned it.
"""
import mcp.types as mt
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult

from lulu_ads.client import LuluAds


class LuluAdsMiddleware(Middleware):
    def __init__(
        self,
        publisher_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        exclude_tools: tuple = (),
        timeout_ms: int = 150,
    ):
        # LuluAds handles env-var defaults and inert mode (no creds -> None,
        # no network) itself; this constructor never raises on missing creds.
        self._ads = LuluAds(publisher_id, api_key, base_url=base_url)
        self._exclude = frozenset(exclude_tools)
        self._timeout_ms = timeout_ms

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next,
    ) -> ToolResult:
        result = await call_next(context)
        try:
            tool_name = context.message.name
            if tool_name in self._exclude:
                return result
            if result.is_error:
                return result
            structured = result.structured_content
            if not isinstance(structured, dict) or "sponsored" in structured:
                return result
            sponsored = await self._ads.sponsored_slot(
                context={"tool": tool_name}, timeout_ms=self._timeout_ms
            )
            if sponsored is not None:
                structured["sponsored"] = sponsored
        except Exception:
            pass  # fail-open: ads may never break a tool result
        return result
