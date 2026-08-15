import os
from dotenv import load_dotenv
import requests
from mcp.server.fastmcp import FastMCP

load_dotenv(override=True)

serper_api_key = os.getenv("SERPER_API_KEY")
serper_url = "https://google.serper.dev/search"

mcp = FastMCP("search_server")


@mcp.tool()
def search(query: str) -> str:
    """Busca en la web y devuelve los resultados más relevantes (título, link, resumen).

    Argumentos:
        query: la consulta de búsqueda a realizar
    """
    headers = {"X-API-KEY": serper_api_key, "Content-Type": "application/json"}
    response = requests.post(serper_url, headers=headers, json={"q": query})
    response.raise_for_status()
    results = response.json().get("organic", [])[:5]
    return "\n\n".join(
        f"{r.get('title')}\n{r.get('link')}\n{r.get('snippet', '')}" for r in results
    ) or "Sin resultados"


if __name__ == "__main__":
    mcp.run(transport="stdio")
