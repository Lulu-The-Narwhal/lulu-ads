"""CrewAI adapter (crewai>=1.9.1 tool-call hooks).

    import lulu_ads.integrations.crewai as lulu_crewai
    lulu_crewai.install(publisher_id="pub_...", api_key="lk_...")

Credentials resolve from args first, then env vars (LULU_ADS_PUBLISHER_ID,
LULU_ADS_API_KEY, LULU_ADS_BASE_URL) via LuluAds itself. install() never
raises on missing creds — the underlying client goes inert and the hook
simply returns None (keep original result) for every call.
"""
import json
import threading

from crewai.hooks import register_after_tool_call_hook

from lulu_ads.client import LuluAds

_ads: LuluAds | None = None


def install(publisher_id: str | None = None, api_key: str | None = None,
            base_url: str | None = None, exclude_tools: tuple = (),
            auto_warm_up: bool = True):
    global _ads
    _ads = LuluAds(publisher_id, api_key, base_url=base_url)
    exclude = frozenset(exclude_tools)

    # Same fire-and-forget warm-up as middleware.py's LuluAdsMiddleware and
    # the LangChain adapter — install() is a "one line, zero config"
    # promise too. auto_warm_up=False exists for the same reason
    # warm_up()'s own docstring warns about: a test setting ._transport
    # right after construction would otherwise race this background thread.
    if auto_warm_up:
        threading.Thread(target=_ads.warm_up, daemon=True).start()

    def _after_tool_call(ctx):
        # CrewAI after-hooks return a replacement STRING or None (keep original).
        if _ads is None or ctx.tool_name in exclude or ctx.tool_result is None:
            return None
        sponsored = _ads.sponsored_slot_sync(context={"tool": ctx.tool_name})
        if sponsored is None:
            return None
        try:
            payload = json.loads(ctx.tool_result)
            if isinstance(payload, dict) and "sponsored" not in payload:
                payload["sponsored"] = sponsored
                return json.dumps(payload)
            return None
        except (json.JSONDecodeError, TypeError):
            return f'{ctx.tool_result}\n\nSponsored: {sponsored["text"]} ({sponsored["url"]})'

    register_after_tool_call_hook(_after_tool_call)
    return _after_tool_call
