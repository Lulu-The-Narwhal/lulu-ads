"""Runnable FastMCP server with one demo tool, monetized in a single line.

    pip install lulu-ads fastmcp
    export LULU_ADS_PUBLISHER_ID=pub_...
    export LULU_ADS_API_KEY=lk_...
    python examples/fastmcp_server.py

Without the env vars set, LuluAdsMiddleware() is inert: it never raises,
never calls the network, and search_flights() just returns unmodified.
"""
from fastmcp import FastMCP

from lulu_ads.middleware import LuluAdsMiddleware

mcp = FastMCP("flight-search-demo")

# One line. Credentials come from LULU_ADS_PUBLISHER_ID / LULU_ADS_API_KEY.
mcp.add_middleware(LuluAdsMiddleware())


@mcp.tool
async def search_flights(origin: str, destination: str, date: str) -> dict:
    """Search flights between two airports on a given date (demo data)."""
    return {
        "origin": origin,
        "destination": destination,
        "date": date,
        "flights": [
            {"carrier": "Demo Air", "price_usd": 412, "stops": 0},
            {"carrier": "Example Airways", "price_usd": 389, "stops": 1},
        ],
    }


if __name__ == "__main__":
    mcp.run()
