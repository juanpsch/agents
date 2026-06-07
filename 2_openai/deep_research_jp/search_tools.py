"""
Search tool implementations. Import the one you want to use in search_agent.py:

    from search_tools import ACTIVE_SEARCH_TOOL

To switch tools, change ACTIVE_SEARCH_TOOL at the bottom of this file.
"""

from agents import WebSearchTool, function_tool


# --- OpenAI WebSearch (paid) ---
openai_search = WebSearchTool(search_context_size="low")


# --- DuckDuckGo (free, no API key) ---
@function_tool
def duckduckgo_search(query: str) -> str:
    """Search the web using DuckDuckGo and return top results as text."""
    from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=5))

    if not results:
        return "No se encontraron resultados."

    return "\n\n".join(
        f"**{r['title']}**\n{r['href']}\n{r['body']}"
        for r in results
    )


# --- Tavily (free tier: 1000 req/mes) ---
@function_tool
def tavily_search(query: str) -> str:
    """Search the web using Tavily and return top results as text."""
    import os
    from tavily import TavilyClient

    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.search(query, max_results=5)

    results = response.get("results", [])
    if not results:
        return "No se encontraron resultados."

    return "\n\n".join(
        f"**{r['title']}**\n{r['url']}\n{r['content']}"
        for r in results
    )


# ---- Cambia esto para elegir la tool activa ----
ACTIVE_SEARCH_TOOL = duckduckgo_search
# ACTIVE_SEARCH_TOOL = openai_search
# ACTIVE_SEARCH_TOOL = tavily_search
