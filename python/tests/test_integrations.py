import json

import httpx
import pytest

GOOD = {"label": "Sponsored", "text": "Lulu Ads", "url": "https://ads.getlulu.dev/c/x"}


def _mock_ads(adapter_owner, response_json=GOOD, status=200):
    adapter_owner._ads._transport = httpx.MockTransport(
        lambda r: httpx.Response(status, json=response_json)
    )


def test_langchain_wrap_tool_call_attaches_sponsored():
    pytest.importorskip("langchain.agents.middleware")
    from langchain.messages import ToolMessage
    from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware

    mw = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x")
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

    mw = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x")
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

    mw = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x", exclude_tools=("private",))
    _mock_ads(mw)

    class Req:
        tool_call = {"name": "private"}

    out = mw.wrap_tool_call(Req(), lambda req: ToolMessage(content="{}", tool_call_id="t"))
    assert "sponsored" not in out.content

    mw2 = LuluAdsAgentMiddleware(publisher_id="pub_1", api_key="lk_x")
    _mock_ads(mw2, status=500)

    class Req2:
        tool_call = {"name": "x"}

    out2 = mw2.wrap_tool_call(Req2(), lambda req: ToolMessage(content='{"a":1}', tool_call_id="t"))
    assert json.loads(out2.content) == {"a": 1}  # backend down → untouched


def test_crewai_hook_attaches_sponsored():
    pytest.importorskip("crewai.hooks")
    from lulu_ads.integrations import crewai as lc

    hook = lc.install(publisher_id="pub_1", api_key="lk_x")
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


def test_format_suffix_none_and_happy_path():
    from lulu_ads import format_suffix

    assert format_suffix(None) == ""
    suffix = format_suffix(GOOD)
    assert "Sponsored:" in suffix
    assert GOOD["text"] in suffix
    assert GOOD["url"] in suffix
