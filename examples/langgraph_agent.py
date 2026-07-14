"""Runnable LangGraph/LangChain agent with monetized tool calls.

    pip install lulu-ads "langchain>=1.0"
    export LULU_ADS_PUBLISHER_ID=pub_...
    export LULU_ADS_API_KEY=lk_...
    python examples/langgraph_agent.py

Without the env vars set, LuluAdsAgentMiddleware() is inert: it never
raises, never calls the network, and tool results pass through unmodified.
"""
from langchain.agents import create_agent
from langchain.tools import tool

from lulu_ads.integrations.langchain import LuluAdsAgentMiddleware


@tool
def search_flights(origin: str, destination: str, date: str) -> dict:
    """Search flights between two airports on a given date (demo data)."""
    return {
        "origin": origin,
        "destination": destination,
        "date": date,
        "flights": [{"carrier": "Demo Air", "price_usd": 412, "stops": 0}],
    }


if __name__ == "__main__":
    # Swap in your real chat model, e.g.:
    #   from langchain.chat_models import init_chat_model
    #   model = init_chat_model("anthropic:claude-sonnet-4-5")
    model = "anthropic:claude-sonnet-4-5"  # placeholder — requires langchain-anthropic + ANTHROPIC_API_KEY

    agent = create_agent(
        model,
        tools=[search_flights],
        middleware=[LuluAdsAgentMiddleware()],
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "Find me a flight TLV to BKK on 2026-09-01"}]}
    )
    print(result["messages"][-1].content)
