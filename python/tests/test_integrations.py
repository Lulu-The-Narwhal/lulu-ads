import asyncio
import json
import threading

import httpx
import pytest

GOOD = {"label": "Sponsored", "text": "Lulu Ads", "url": "https://ads.getlulu.dev/c/x"}


def test_langchain_auto_warm_up_fires_by_default(monkeypatch):
    pytest.importorskip("langchain.agents.middleware")
    from lulu_ads.client import LuluAds
    from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

    fired = threading.Event()
    monkeypatch.setattr(LuluAds, "warm_up", lambda self: fired.set())
    LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x")
    assert fired.wait(timeout=1.0), "warm_up() was not called from a background thread"


def test_langchain_auto_warm_up_false_never_fires(monkeypatch):
    pytest.importorskip("langchain.agents.middleware")
    from lulu_ads.client import LuluAds
    from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

    fired = threading.Event()
    monkeypatch.setattr(LuluAds, "warm_up", lambda self: fired.set())
    LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
    assert not fired.wait(timeout=0.2)


def _mock_ads(adapter_owner, response_json=GOOD, status=200):
    adapter_owner._ads._transport = httpx.MockTransport(
        lambda r: httpx.Response(status, json=response_json)
    )


def test_langchain_wrap_tool_call_attaches_sponsored():
    pytest.importorskip("langchain.agents.middleware")
    from langchain.messages import ToolMessage
    from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

    mw = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
    _mock_ads(mw)

    class Req:  # minimal ToolCallRequest stand-in: adapter only touches .tool_call["name"]
        tool_call = {"name": "search_flights"}

    original = ToolMessage(content=json.dumps({"flights": [1]}), tool_call_id="t1")
    out = mw.wrap_tool_call(Req(), lambda req: original)
    assert json.loads(out.content)["sponsored"] == GOOD
    assert json.loads(out.content)["flights"] == [1]


def test_langchain_non_json_content_uses_additional_kwargs():
    pytest.importorskip("langchain.agents.middleware")
    from langchain.messages import ToolMessage
    from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

    mw = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
    _mock_ads(mw)

    class Req:
        tool_call = {"name": "search_flights"}

    out = mw.wrap_tool_call(Req(), lambda req: ToolMessage(content="plain text", tool_call_id="t1"))
    assert out.content == "plain text"
    assert out.additional_kwargs["sponsored"] == GOOD


def test_langchain_excluded_and_failopen():
    pytest.importorskip("langchain.agents.middleware")
    from langchain.messages import ToolMessage
    from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

    mw = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x", exclude_tools=("private",), auto_warm_up=False)
    _mock_ads(mw)

    class Req:
        tool_call = {"name": "private"}

    out = mw.wrap_tool_call(Req(), lambda req: ToolMessage(content="{}", tool_call_id="t"))
    assert "sponsored" not in out.content

    mw2 = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
    _mock_ads(mw2, status=500)

    class Req2:
        tool_call = {"name": "x"}

    out2 = mw2.wrap_tool_call(Req2(), lambda req: ToolMessage(content='{"a":1}', tool_call_id="t"))
    assert json.loads(out2.content) == {"a": 1}  # backend down → untouched


def test_langchain_existing_sponsored_key_skipped():
    pytest.importorskip("langchain.agents.middleware")
    from langchain.messages import ToolMessage
    from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

    mw = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
    _mock_ads(mw)

    class Req:
        tool_call = {"name": "search_flights"}

    original_content = json.dumps(
        {"a": 1, "sponsored": {"label": "Sponsored", "text": "orig", "url": "u"}}
    )
    out = mw.wrap_tool_call(Req(), lambda req: ToolMessage(content=original_content, tool_call_id="t1"))
    assert out.content == original_content
    assert "sponsored" not in out.additional_kwargs


async def test_langchain_awrap_tool_call_attaches_sponsored():
    pytest.importorskip("langchain.agents.middleware")
    from langchain.messages import ToolMessage
    from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

    mw = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
    _mock_ads(mw)

    class Req:
        tool_call = {"name": "search_flights"}

    original = ToolMessage(content=json.dumps({"flights": [1]}), tool_call_id="t1")

    async def handler(req):
        return original

    out = await mw.awrap_tool_call(Req(), handler)
    assert json.loads(out.content)["sponsored"] == GOOD
    assert json.loads(out.content)["flights"] == [1]


def test_langchain_middleware_inert_no_creds(monkeypatch):
    pytest.importorskip("langchain.agents.middleware")
    from langchain.messages import ToolMessage
    from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

    monkeypatch.delenv("LULU_ADS_PUBLISHER_ID", raising=False)
    monkeypatch.delenv("LULU_ADS_API_KEY", raising=False)
    monkeypatch.delenv("LULU_ADS_BASE_URL", raising=False)

    mw = LuluAdsAgentMiddleware(auto_warm_up=False)
    assert mw._ads._is_inert()

    calls = []
    mw._ads._transport = httpx.MockTransport(
        lambda r: (calls.append(r), httpx.Response(200, json=GOOD))[1]
    )

    class Req:
        tool_call = {"name": "search_flights"}

    original = ToolMessage(content=json.dumps({"flights": [1]}), tool_call_id="t1")
    out = mw.wrap_tool_call(Req(), lambda req: original)
    assert out is original
    assert json.loads(out.content) == {"flights": [1]}
    assert calls == []


def test_crewai_install_auto_warm_up_fires_by_default(monkeypatch):
    pytest.importorskip("crewai.hooks")
    from crewai.hooks import unregister_after_tool_call_hook
    from lulu_ads.client import LuluAds
    from lulu_ads.integrations import crewai as lc

    fired = threading.Event()
    monkeypatch.setattr(LuluAds, "warm_up", lambda self: fired.set())
    hook = lc.install(publisher_id="pub_1", api_key="lk_x")
    try:
        assert fired.wait(timeout=1.0), "warm_up() was not called from a background thread"
    finally:
        unregister_after_tool_call_hook(hook)


def test_crewai_install_auto_warm_up_false_never_fires(monkeypatch):
    pytest.importorskip("crewai.hooks")
    from crewai.hooks import unregister_after_tool_call_hook
    from lulu_ads.client import LuluAds
    from lulu_ads.integrations import crewai as lc

    fired = threading.Event()
    monkeypatch.setattr(LuluAds, "warm_up", lambda self: fired.set())
    hook = lc.install(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
    try:
        assert not fired.wait(timeout=0.2)
    finally:
        unregister_after_tool_call_hook(hook)


def test_crewai_hook_attaches_sponsored():
    pytest.importorskip("crewai.hooks")
    from lulu_ads.integrations import crewai as lc

    hook = lc.install(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)
    try:
        _mock_ads(lc)

        class Ctx:  # ToolCallHookContext stand-in: hook reads .tool_name / .tool_result
            tool_name = "search_flights"
            tool_result = json.dumps({"flights": [1]})

        out = hook(Ctx())
        assert json.loads(out)["sponsored"] == GOOD
    finally:
        from crewai.hooks import unregister_after_tool_call_hook
        unregister_after_tool_call_hook(hook)


def test_crewai_install_inert_no_creds(monkeypatch):
    pytest.importorskip("crewai.hooks")
    from lulu_ads.integrations import crewai as lc

    monkeypatch.delenv("LULU_ADS_PUBLISHER_ID", raising=False)
    monkeypatch.delenv("LULU_ADS_API_KEY", raising=False)
    monkeypatch.delenv("LULU_ADS_BASE_URL", raising=False)

    hook = lc.install(auto_warm_up=False)
    try:
        assert lc._ads._is_inert()

        calls = []
        lc._ads._transport = httpx.MockTransport(
            lambda r: (calls.append(r), httpx.Response(200, json=GOOD))[1]
        )

        class Ctx:
            tool_name = "search_flights"
            tool_result = json.dumps({"flights": [1]})

        out = hook(Ctx())
        assert out is None
        assert calls == []
    finally:
        from crewai.hooks import unregister_after_tool_call_hook
        unregister_after_tool_call_hook(hook)


async def test_langchain_async_warm_up_fires_via_abefore_agent(monkeypatch):
    pytest.importorskip("langchain.agents.middleware")
    from lulu_ads.client import LuluAds
    from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

    monkeypatch.setattr(LuluAds, "warm_up", lambda self: None)
    fired = asyncio.Event()

    async def fake_async_warm_up(self):
        fired.set()

    monkeypatch.setattr(LuluAds, "async_warm_up", fake_async_warm_up)

    mw = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x")
    await mw.abefore_agent(state=None, runtime=None)
    await asyncio.wait_for(fired.wait(), timeout=1.0)


async def test_langchain_async_warm_up_fires_only_once(monkeypatch):
    pytest.importorskip("langchain.agents.middleware")
    from lulu_ads.client import LuluAds
    from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

    monkeypatch.setattr(LuluAds, "warm_up", lambda self: None)
    call_count = {"n": 0}

    async def fake_async_warm_up(self):
        call_count["n"] += 1

    monkeypatch.setattr(LuluAds, "async_warm_up", fake_async_warm_up)

    mw = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x")
    await mw.abefore_agent(state=None, runtime=None)
    await mw.abefore_agent(state=None, runtime=None)
    await asyncio.sleep(0.05)
    assert call_count["n"] == 1


def test_langchain_async_warm_up_never_fires_when_auto_warm_up_false(monkeypatch):
    pytest.importorskip("langchain.agents.middleware")
    from lulu_ads.client import LuluAds
    from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

    fired = []

    async def fake_async_warm_up(self):
        fired.append(1)

    monkeypatch.setattr(LuluAds, "async_warm_up", fake_async_warm_up)
    mw = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x", auto_warm_up=False)

    async def run():
        await mw.abefore_agent(state=None, runtime=None)

    asyncio.run(run())
    assert fired == []


def test_format_suffix_none_and_happy_path():
    from lulu_ads import format_suffix

    assert format_suffix(None) == ""
    suffix = format_suffix(GOOD)
    assert "Sponsored:" in suffix
    assert GOOD["text"] in suffix
    assert GOOD["url"] in suffix
