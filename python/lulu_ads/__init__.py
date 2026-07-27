from lulu_ads.client import LuluAds, format_suffix

__all__ = ["LuluAds", "format_suffix"]
__version__ = "0.7.0"

# lulu_ads.widget (claude_apps_domain, sponsored_widget_html,
# register_sponsored_widget) is not imported here — it requires fastmcp,
# which is not a hard dependency of this package. Import it directly:
#   from lulu_ads.widget import register_sponsored_widget
