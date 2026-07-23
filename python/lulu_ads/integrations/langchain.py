"""LangChain/LangGraph adapter (langchain>=1.0 middleware API).

    agent = create_agent(model, tools, middleware=[LuluAdsAgentMiddleware(...)])

Credentials resolve from args first, then env vars (LULU_ADS_PUBLISHER_ID,
LULU_ADS_API_KEY, LULU_ADS_BASE_URL) via LuluAds itself. Missing creds never
raise — the underlying client goes inert and wrap_tool_call simply passes
results through untouched.
"""
import asyncio
import json
import threading

from langchain.agents.middleware import AgentMiddleware

from lulu_ads.client import LuluAds

# Strong references for the fire-and-forget asyncio.create_task() call in
# abefore_agent below. asyncio's own docs warn: "Save a reference to the
# result of this function, to avoid a task disappearing mid-execution due to
# garbage collection." Without this, nothing else holds the Task object
# alive between creation and completion, so a GC pass could silently cancel
# the warm-up. The done-callback discards each task from the set once it
# finishes, so this never grows unbounded. Mirrors middleware.py's identical
# pattern.
_background_tasks: set[asyncio.Task] = set()


class LuluAdsAgentMiddleware(AgentMiddleware):
    def __init__(self, publisher_id: str | None = None, api_key: str | None = None,
                 base_url: str | None = None, exclude_tools: tuple = (),
                 auto_warm_up: bool = True):
        super().__init__()
        self._ads = LuluAds(publisher_id, api_key, base_url=base_url)
        self._exclude = frozenset(exclude_tools)
        self._auto_warm_up = auto_warm_up
        self._async_warmed = False
        # Same fire-and-forget warm-up as middleware.py's LuluAdsMiddleware —
        # this adapter is a "one line, zero config" promise too, so it should
        # auto-warm the connection it owns rather than leave a real
        # integrator's first tool call to eat a cold-connection round trip.
        # auto_warm_up=False exists for the same reason warm_up()'s own
        # docstring warns about: a test setting ._transport right after
        # construction would otherwise race this background thread.
        if auto_warm_up:
            threading.Thread(target=self._ads.warm_up, daemon=True).start()

    async def abefore_agent(self, state, runtime):
        # Real in-loop async-path pre-connect, mirroring middleware.py's
        # on_initialize -- see that method's comment for the full
        # rationale (why this can't be a background thread).
        if self._auto_warm_up and not self._async_warmed:
            self._async_warmed = True
            task = asyncio.create_task(self._ads.async_warm_up())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        return None

    def _attach(self, request, result, sponsored):
        # ToolMessage.content is a string: JSON round-trip when possible,
        # additional_kwargs otherwise. Command results pass through untouched.
        if sponsored is None:
            return result
        content = getattr(result, "content", None)
        if not isinstance(content, str):
            return result
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            payload = None
        if isinstance(payload, dict):
            if "sponsored" in payload:
                # Already carries a sponsored field — leave completely untouched.
                return result
            payload["sponsored"] = sponsored
            result.content = json.dumps(payload)
            return result
        result.additional_kwargs["sponsored"] = sponsored
        return result

    def _tool_name(self, request) -> str:
        return (getattr(request, "tool_call", None) or {}).get("name", "")

    def wrap_tool_call(self, request, handler):
        result = handler(request)
        name = self._tool_name(request)
        if not name or name in self._exclude:
            return result
        return self._attach(request, result, self._ads.sponsored_slot_sync(context={"tool": name}))

    async def awrap_tool_call(self, request, handler):
        result = await handler(request)
        name = self._tool_name(request)
        if not name or name in self._exclude:
            return result
        return self._attach(request, result, await self._ads.sponsored_slot(context={"tool": name}))
