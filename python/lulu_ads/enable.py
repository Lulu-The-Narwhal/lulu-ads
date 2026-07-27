"""enable_lulu_ads(mcp, endpoint_url=...) -- one call that monetizes every
tool on a FastMCP server AND gives every one of them the rendered
Sponsored-card widget in hosts that support MCP Apps (e.g. Claude.ai).

Before this existed, getting the widget required two extra, easy-to-forget
manual steps beyond the middleware one-liner: calling
register_sponsored_widget() once, and then remembering to add
``app=that_config`` to every single ``@mcp.tool(...)`` you wanted it on. Live
audit of our own dogfood server (Dali) found exactly this gap: the widget was
wired onto ONE tool by hand months ago, and every tool added since then
quietly never got it -- nothing enforced it, so it silently rotted. The
middleware's own guarantee ("every tool gets a sponsored field") was never
true for the widget half of that promise.

This closes that gap the same way the middleware closes it for the data
field: by wrapping ``mcp.tool`` itself (same pattern the TS SDK already uses
to wrap ``registerTool`` in mcp.ts), so every tool registered AFTER this call
gets the widget automatically, with no per-tool action required and no way
to forget it on a newly added tool.

Usage::

    from fastmcp import FastMCP
    from lulu_ads.enable import enable_lulu_ads

    mcp = FastMCP("my-server")
    enable_lulu_ads(mcp, endpoint_url="https://my-server.example.com/mcp")

    @mcp.tool
    def search(...): ...  # already monetized AND already widget-enabled
"""
from lulu_ads.middleware import LuluAdsMiddleware
from lulu_ads.widget import register_sponsored_widget


def enable_lulu_ads(
    mcp,
    *,
    endpoint_url: str,
    publisher_id: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    exclude_tools: tuple = (),
    timeout_ms: int | None = None,
    cli_text_mode: bool = False,
    auto_warm_up: bool = True,
    resource_uri: str = "ui://lulu-ads/sponsored.html",
):
    """Wires LuluAdsMiddleware AND the sponsored-card widget onto every tool
    on `mcp`, present and future. `endpoint_url` must be the exact public MCP
    connector URL clients connect to (see widget.py's claude_apps_domain --
    the widget silently never renders if this doesn't match).

    `exclude_tools` is honored by BOTH halves (no ad data, no widget) --
    passed straight through to LuluAdsMiddleware and independently checked
    here before the widget's `app` config is injected into a tool's
    registration.

    `text`/`url`/`logo` aren't exposed here because the widget never
    actually shows them: it starts in a loading skeleton and only ever
    renders once a live tool-result carries real `sponsored` data (see
    widget.py's docstring) -- passing per-integration placeholder ad copy at
    setup time would just be dead code.

    Returns `mcp` for chaining, same as `withLuluAds` on the TS side.
    """
    mcp.add_middleware(
        LuluAdsMiddleware(
            publisher_id=publisher_id,
            api_key=api_key,
            base_url=base_url,
            exclude_tools=exclude_tools,
            timeout_ms=timeout_ms,
            cli_text_mode=cli_text_mode,
            auto_warm_up=auto_warm_up,
        )
    )

    app_config = register_sponsored_widget(
        mcp,
        endpoint_url=endpoint_url,
        text="Sponsored",
        url=endpoint_url,
        resource_uri=resource_uri,
    )

    exclude = frozenset(exclude_tools)
    orig_tool = mcp.tool

    def _resolve_name(name_or_fn, kwargs) -> str | None:
        if "name" in kwargs:
            return kwargs["name"]
        if isinstance(name_or_fn, str):
            return name_or_fn
        if callable(name_or_fn):
            return getattr(name_or_fn, "__name__", None)
        return None

    def _with_app(name_or_fn, kwargs):
        # Never override a tool's own explicit app= -- an integrator who
        # deliberately set their own widget (or app=False to opt out) made
        # a real choice, same as timeout_ms/enabled elsewhere in this SDK.
        if "app" in kwargs:
            return kwargs
        name = _resolve_name(name_or_fn, kwargs)
        if name in exclude:
            return kwargs
        return {**kwargs, "app": app_config}

    def wrapped_tool(name_or_fn=None, **kwargs):
        # mcp.tool supports three call shapes: bare `@mcp.tool`
        # (name_or_fn IS the function), `@mcp.tool("name")`, and
        # `@mcp.tool(name=..., ...)` / `@mcp.tool()` (returns a decorator).
        # Only the first can resolve app= immediately; the other two must
        # wait until the decorator is actually applied to a function to
        # know the real name when it falls back to fn.__name__.
        if callable(name_or_fn) and not isinstance(name_or_fn, str):
            return orig_tool(name_or_fn, **_with_app(name_or_fn, kwargs))

        def decorator(fn):
            return orig_tool(name_or_fn, **_with_app(fn if name_or_fn is None else name_or_fn, kwargs))(fn)

        return decorator

    mcp.tool = wrapped_tool
    return mcp
