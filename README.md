# Lulu Ads

Disclosed sponsored slots for MCP servers and AI agent tools. Ships data, never directives. Fail-open by design.

## Installation

```bash
pip install lulu-ads
```

## Usage

```python
from lulu_ads import LuluAds

ads = LuluAds(publisher_id="your_id", api_key="your_key")
result = await ads.sponsored_slot(context={"tool": "search_flights"})
```
