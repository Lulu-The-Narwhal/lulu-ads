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

from lulu_ads.cli_card import format_cli_card, is_cli_client
from lulu_ads.client import LuluAds


def _connected_client_name(context: MiddlewareContext) -> str | None:
    """Best-effort read of the MCP clientInfo.name sent at initialize.
    Returns None on any failure — this must never break a tool call.
    """
    try:
        return context.fastmcp_context.session.client_params.clientInfo.name
    except Exception:
        return None


class LuluAdsMiddleware(Middleware):
    def __init__(
        self,
        publisher_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        exclude_tools: tuple = (),
        timeout_ms: int | None = None,
    ):
        # LuluAds handles env-var defaults and inert mode (no creds -> None,
        # no network) itself; this constructor never raises on missing creds.
        #
        # timeout_ms defaults to None (client.py's own conditional
        # 800ms/3000ms default), not a fixed number -- a hardcoded 300ms
        # here was found live (not in this file's own mocked tests, which
        # respond instantly and can never catch this) to fail consistently
        # against a real cold ads-server call: real round-trip time for a
        # category-only match sits close enough to 300ms that it has no
        # real margin, while the SDK's own smart default succeeded on every
        # real attempt. Every test in this file uses an instant
        # MockTransport, which is exactly why this shipped unnoticed —
        # mocked tests can prove correctness, never prove a timeout is
        # actually sufficient for real latency.
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
                client_name = _connected_client_name(context)
                if is_cli_client(client_name):
                    # Terminals have no widget surface — the model's own text
                    # is the only rendering there is. Append a bordered
                    # plain-text card to content[] so it's visually distinct
                    # from a plain sentence, without touching the model's own
                    # words or telling it what to say.
                    result.content.append(mt.TextContent(type="text", text=format_cli_card(sponsored)))
        except Exception:
            pass  # fail-open: ads may never break a tool result
        return result
