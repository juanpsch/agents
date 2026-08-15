import os
from dotenv import load_dotenv
from market import is_paid_polygon, is_realtime_polygon

load_dotenv(override=True)


def full_env(overrides: dict | None = None) -> dict:
    """El SDK de MCP solo hereda un puñado de env vars (HOME, PATH, etc.) a los
    subprocesos, no HTTP_PROXY/HTTPS_PROXY. Mezclamos con os.environ para que
    los servidores MCP puedan salir a internet a través del proxy corporativo."""
    return {**os.environ, **(overrides or {})}



polygon_api_key = os.getenv("POLYGON_API_KEY")

# El servidor MCP para que el Trader lea datos de mercado

if is_paid_polygon or is_realtime_polygon:
    market_mcp = {
        "command": "uvx",
        "args": ["--from", "git+https://github.com/polygon-io/mcp_polygon@master", "mcp_polygon"],
        "env": full_env({"POLYGON_API_KEY": polygon_api_key}),
    }
else:
    market_mcp = {"command": "uv", "args": ["run", "market_server.py"], "env": full_env()}


# El conjunto completo de servidores MCP para el trader: Cuentas, Notificaciones Push y Mercado

trader_mcp_server_params = [
    {"command": "uv", "args": ["run", "accounts_server.py"], "env": full_env()},
    {"command": "uv", "args": ["run", "push_server.py"], "env": full_env()},
    market_mcp,
]

# El conjunto completo de servidores MCP para el investigador: Fetch, (Brave Search o Serper, lo que tengamos key) y Memoria


def researcher_mcp_server_params(name: str):
    servers = [
        {"command": "uvx", "args": ["--with", "mcp<2", "mcp-server-fetch"], "env": full_env()},
    ]

    brave_api_key = os.getenv("BRAVE_API_KEY")
    if brave_api_key:
        servers.append({
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            "env": full_env({"BRAVE_API_KEY": brave_api_key}),
        })

    serper_api_key = os.getenv("SERPER_API_KEY")
    if serper_api_key:
        servers.append({"command": "uv", "args": ["run", "search_server.py"], "env": full_env()})

    servers.append({
        "command": "npx",
        "args": ["-y", "mcp-memory-libsql"],
        "env": full_env({"LIBSQL_URL": f"file:./memory/{name}.db"}),
    })

    return servers
