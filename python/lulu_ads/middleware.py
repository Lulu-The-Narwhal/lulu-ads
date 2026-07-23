"""One-line monetization for FastMCP servers.

    mcp.add_middleware(LuluAdsMiddleware())

Attaches a labeled `sponsored` data field to tool results. Never a directive,
never on excluded tools, never on existing `sponsored` keys, never on errors,
and never able to break the tool: any ads failure (missing credentials,
network error, timeout, malformed response) leaves the result exactly as the
tool returned it.
"""
import asyncio
import threading

import mcp.types as mt
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult

from lulu_ads.cli_card import format_cli_card, is_cli_client
from lulu_ads.client import LuluAds

# Strong references for fire-and-forget asyncio.create_task() calls below.
# asyncio's own docs warn: "Save a reference to the result of this function,
# to avoid a task disappearing mid-execution due to garbage collection."
# Without this, nothing else holds the Task object alive between creation and
# completion, so a GC pass could silently cancel the warm-up -- the exact
# "async path isn't actually warmed" failure this file exists to fix. The
# done-callback discards each task from the set once it finishes, so this
# never grows unbounded.
_background_tasks: set[asyncio.Task] = set()


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
        auto_warm_up: bool = True,
    ):
        # LuluAds handles env-var defaults and inert mode (no creds -> None,
        # no network) itself; this constructor never raises on missing creds.
        #
        # timeout_ms defaults to None (client.py's own conditional
        # 800ms/3000ms default), not a fixed number -- a hardcoded 300ms
        # here was found live (not in this file's own mocked tests, which
        # respond instantly and can never catch this) to fail consistently
        # against a real cold ads-server call. Every test in this file uses
        # an instant MockTransport, which is exactly why this shipped
        # unnoticed -- mocked tests can prove correctness, never prove a
        # timeout is actually sufficient for real latency.
        self._ads = LuluAds(publisher_id, api_key, base_url=base_url)
        self._exclude = frozenset(exclude_tools)
        self._timeout_ms = timeout_ms
        self._auto_warm_up = auto_warm_up
        self._async_warmed = False

        # Fire-and-forget warm-up: found live, first real tool call on a
        # freshly started server measured 804ms against the 800ms
        # fast-path default -- a genuinely cold connection (fresh TLS/DNS)
        # sits right at that ceiling, not comfortably under it. A raw
        # LuluAds client deliberately never auto-warms (a real network call
        # as a __init__ side effect is surprising in a general-purpose
        # client used in test-sensitive contexts) -- but this middleware
        # IS the "one line, zero config" promise itself, so warming here is
        # the one place doing it automatically is the right default rather
        # than quietly undercutting that promise on every server's very
        # first real request. auto_warm_up=False exists for exactly the
        # case warm_up()'s own docstring warns about: a test setting
        # ._transport right after construction (this file's own
        # make_middleware() helper) would otherwise race a background
        # thread already headed for the real network.
        if auto_warm_up:
            threading.Thread(target=self._ads.warm_up, daemon=True).start()

    async def on_initialize(
        self,
        context: MiddlewareContext[mt.InitializeRequest],
        call_next,
    ):
        # Real in-loop async-path pre-connect: on_initialize runs on the
        # actual serving event loop, before any tool call (every MCP
        # client sends initialize first) -- unlike the sync warm_up()
        # thread, this can safely warm the ASYNC client's connection
        # too, since it executes on the same loop sponsored_slot() will
        # later use. Fired once (guarded), never awaited inline so it
        # can never delay this handshake response.
        if self._auto_warm_up and not self._async_warmed:
            self._async_warmed = True
            task = asyncio.create_task(self._ads.async_warm_up())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        return await call_next(context)

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
