"""Runnable(-ish) CrewAI crew with monetized tool calls.

    pip install lulu-ads "crewai>=1.9.1"
    export LULU_ADS_PUBLISHER_ID=pub_...
    export LULU_ADS_API_KEY=lk_...
    python examples/crewai_crew.py

install() registers a global after-tool-call hook once, before any crew
runs. Without the env vars set it's inert: it never raises, never calls the
network, and tool results pass through unmodified. kickoff() is commented
out below since it requires a configured LLM provider key — everything
above that line runs standalone.
"""
from crewai import Agent, Crew, Task
from crewai.tools import tool

import lulu_ads.integrations.crewai as lulu_crewai

# Call once, at process/crew startup, before kickoff().
lulu_crewai.install()


@tool("search_flights")
def search_flights(origin: str, destination: str, date: str) -> str:
    """Search flights between two airports on a given date (demo data)."""
    return f"{origin} -> {destination} on {date}: Demo Air, $412, nonstop"


travel_agent = Agent(
    role="Travel researcher",
    goal="Find flight options for the traveler's request",
    backstory="An assistant that looks up flights on request.",
    tools=[search_flights],
)

find_flight_task = Task(
    description="Find flights from TLV to BKK on 2026-09-01",
    expected_output="A short list of flight options with price and stops",
    agent=travel_agent,
)

crew = Crew(agents=[travel_agent], tasks=[find_flight_task])

if __name__ == "__main__":
    # result = crew.kickoff()
    # print(result)
    pass
