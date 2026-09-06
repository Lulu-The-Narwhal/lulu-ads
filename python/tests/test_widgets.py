"""Tests for lulu_ads.widgets -- the result-widget template gallery.

Snapshot-style: the HTML is generated, so tests assert on the stable,
load-bearing fragments (template wiring, config injection + escaping, the
fixed strip, the canvas fix) rather than byte-golden files that would
churn on every CSS tweak.
"""
import asyncio
import json

import pytest

from lulu_ads.widgets import (
    TEMPLATES,
    register_result_widget,
    result_widget_html,
)


def test_all_four_templates_render():
    for template in TEMPLATES:
        html = result_widget_html(template=template, mapping={"eyebrow": "x"})
        assert f'var TEMPLATE = "{template}";' in html


def test_unknown_template_raises():
    with pytest.raises(ValueError, match="unknown template"):
        result_widget_html(template="hero-card", mapping={})


def test_frame_carries_the_non_negotiables():
    html = result_widget_html(template="stat-card", mapping={})
    # transparent canvas (the 0.7.4 color-scheme fix)
    assert "color-scheme: light dark" in html
    # host bridge contract
    assert "ui/notifications/initialized" in html
    assert "ui/notifications/size-changed" in html
    assert "ui/notifications/tool-result" in html
    assert "ui/open-link" in html
    # the fixed SPONSORED strip + sheen + reduced-motion opt-out
    assert "SPONSORED" in html
    assert "via Lulu Ads" in html
    assert "lw-shine" in html
    assert "prefers-reduced-motion" in html
    # logo tile + letter fallback machinery
    assert "logo_url" in html
    assert "letterTile" in html


def test_table_card_row_link_capability_is_embedded():
    html = result_widget_html(
        template="table-card",
        mapping={"rows": "flights", "columns": [], "rowLink": "booking_url"},
    )
    # the rowLink mapping key must ride through into the embedded config...
    assert "booking_url" in html
    # ...and the renderer must wire it to the same host-agnostic opener
    # the sponsored strip already uses, not a fresh/second link mechanism.
    assert "rowUrl" in html and "openLink(String(rowUrl))" in html
    assert "tr.linked" in html


def test_mapping_rides_an_escaped_attribute():
    mapping = {"eyebrow": 'x"onmouseover="alert(1)', "value": "temp"}
    html = result_widget_html(template="stat-card", mapping=mapping)
    # the raw quote must never appear unescaped inside the attribute
    # (json.dumps backslash-escapes it, then _escape_html entity-escapes:
    # `x"` -> `x\"` -> `x\&quot;`)
    assert 'x"onmouseover' not in html
    assert 'x\\&quot;onmouseover' in html
    # and the config parses back to the same mapping via getAttribute
    assert 'getAttribute("data-lw-config")' in html


def test_body_html_escape_hatch_is_embedded():
    html = result_widget_html(
        template="stat-card",
        mapping={},
        body_html='<div class="lw-value">42</div>',
    )
    cfg = json.dumps({"mapping": {}, "bodyHtml": '<div class="lw-value">42</div>'},
                     separators=(",", ":"), ensure_ascii=False)
    from lulu_ads.widget import _escape_html
    assert _escape_html(cfg) in html


def _fresh_mcp():
    from fastmcp import FastMCP
    return FastMCP("test-widgets")


def test_register_patches_registered_tool_meta():
    mcp = _fresh_mcp()

    @mcp.tool
    def lookup(q: str) -> dict:
        """d"""
        return {"q": q}

    cfg = register_result_widget(
        mcp, "lookup",
        template="table-card",
        mapping={"rows": "items"},
        endpoint_url="https://example.com/mcp",
    )
    tool = asyncio.run(mcp.get_tool("lookup"))
    assert tool.meta["ui"]["resourceUri"] == "ui://lulu-ads/result-lookup.html"
    assert tool.meta["ui"]["visibility"] == ["model"]
    assert tool.meta["openai/outputTemplate"] == "ui://lulu-ads/result-lookup.html"
    # CopilotKit's MCPAppsMiddleware only discovers UI tools via this flat
    # key -- see the comment above ui_meta in widgets.py for why.
    assert tool.meta["ui/resourceUri"] == "ui://lulu-ads/result-lookup.html"
    # and the returned AppConfig matches, for the explicit app= path
    assert cfg.resource_uri == "ui://lulu-ads/result-lookup.html"


def test_register_overrides_enable_lulu_ads_generic_card():
    from lulu_ads.enable import enable_lulu_ads

    mcp = _fresh_mcp()
    enable_lulu_ads(mcp, endpoint_url="https://example.com/mcp", auto_warm_up=False)

    @mcp.tool
    def check(q: str) -> dict:
        """d"""
        return {"q": q}

    tool = asyncio.run(mcp.get_tool("check"))
    assert tool.meta["ui"]["resourceUri"] == "ui://lulu-ads/sponsored.html"

    register_result_widget(
        mcp, "check",
        template="notice-card",
        mapping={"title": "q"},
        endpoint_url="https://example.com/mcp",
    )
    tool = asyncio.run(mcp.get_tool("check"))
    assert tool.meta["ui"]["resourceUri"] == "ui://lulu-ads/result-check.html"


def test_register_registers_the_resource_with_claude_domain():
    from lulu_ads.widget import claude_apps_domain

    mcp = _fresh_mcp()

    @mcp.tool
    def t1(q: str) -> dict:
        """d"""
        return {"q": q}

    register_result_widget(
        mcp, "t1", template="carousel-card",
        mapping={"items": "options"},
        endpoint_url="https://example.com/mcp",
    )
    resources = asyncio.run(mcp._list_resources())
    uris = [str(r.uri) for r in resources]
    assert "ui://lulu-ads/result-t1.html" in uris
    assert claude_apps_domain("https://example.com/mcp").endswith(".claudemcpcontent.com")


def test_register_before_tool_registration_returns_usable_config():
    mcp = _fresh_mcp()
    cfg = register_result_widget(
        mcp, "later",
        template="stat-card",
        mapping={"value": "n"},
        endpoint_url="https://example.com/mcp",
    )

    @mcp.tool(app=cfg)
    def later(q: str) -> dict:
        """d"""
        return {"q": q}

    tool = asyncio.run(mcp.get_tool("later"))
    assert tool.meta["ui"]["resourceUri"] == "ui://lulu-ads/result-later.html"


# ── sponsor_template (LUL-69: flip-card in the result-widget footer) ────

def test_result_widget_defaults_sponsor_template_to_card():
    html = result_widget_html(template="stat-card", mapping={})
    assert 'var SPONSOR_TEMPLATE = "card";' in html


def test_result_widget_accepts_flip_card_sponsor_template():
    html = result_widget_html(template="table-card", mapping={}, sponsor_template="flip-card")
    assert 'var SPONSOR_TEMPLATE = "flip-card";' in html


def test_result_widget_rejects_unknown_sponsor_template():
    with pytest.raises(ValueError, match="unknown sponsor_template"):
        result_widget_html(template="stat-card", mapping={}, sponsor_template="hero")


def test_result_widget_flip_card_strip_markup_present_regardless_of_sponsor_template():
    # Both faces' DOM always ships in the frame -- JS decides which to
    # show based on SPONSOR_TEMPLATE, not server-side conditional markup
    # (same pattern `template`'s own RENDERERS dispatch already uses).
    html = result_widget_html(template="stat-card", mapping={})
    assert 'id="strip-flip"' in html
    assert 'id="sp-text-flip"' in html
    assert 'id="strip-back"' in html


def test_register_result_widget_passes_sponsor_template_through():
    mcp = _fresh_mcp()

    @mcp.tool
    def lookup2(q: str) -> dict:
        """d"""
        return {"q": q}

    register_result_widget(
        mcp, "lookup2",
        template="table-card",
        mapping={"rows": "items"},
        endpoint_url="https://example.com/mcp",
        sponsor_template="flip-card",
    )
    resources = asyncio.run(mcp._list_resources())
    [r] = [r for r in resources if str(r.uri) == "ui://lulu-ads/result-lookup2.html"]
    html = asyncio.run(r.read())
    assert 'var SPONSOR_TEMPLATE = "flip-card";' in str(html)


def test_result_widget_accepts_carousel_and_scratch_reveal_sponsor_templates():
    for name in ("carousel", "scratch-reveal"):
        html = result_widget_html(template="stat-card", mapping={}, sponsor_template=name)
        assert f'var SPONSOR_TEMPLATE = "{name}";' in html


def test_flip_card_front_face_has_a_cta():
    # Regression: the front teaser originally had no CTA/prompt at all --
    # just the bare disclosure label -- giving nobody a reason to tap it.
    html = result_widget_html(template="stat-card", mapping={}, sponsor_template="flip-card")
    assert "Tap to reveal" in html


def test_scratch_reveal_canvas_markup_present():
    html = result_widget_html(template="stat-card", mapping={})
    assert 'id="scratch-canvas"' in html


def test_carousel_track_and_dots_markup_present():
    html = result_widget_html(template="stat-card", mapping={})
    assert 'id="carousel-track"' in html
    assert 'id="carousel-dots"' in html


def test_spin_is_not_a_valid_sponsor_template():
    # spin shipped, turned out visually illegible (a coin-flip scaleX on a
    # small, often-flat letter-tile logo shrinks to a near-invisible sliver
    # mid-animation), and was replaced by carousel rather than patched.
    with pytest.raises(ValueError, match="unknown sponsor_template"):
        result_widget_html(template="stat-card", mapping={}, sponsor_template="spin")
