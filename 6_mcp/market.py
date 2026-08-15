from dotenv import load_dotenv
import os
import requests
from datetime import datetime
import random
from database import write_market, read_market
from functools import lru_cache
from datetime import timezone

load_dotenv(override=True)

polygon_api_key = os.getenv("POLYGON_API_KEY")
polygon_plan = os.getenv("POLYGON_PLAN")

is_paid_polygon = polygon_plan == "paid"
is_realtime_polygon = polygon_plan == "realtime"

POLYGON_BASE_URL = "https://api.polygon.io"


def _polygon_get(path: str, **params) -> dict:
    """Le pega directo a la REST API de Polygon con requests, que sí respeta
    HTTP_PROXY/HTTPS_PROXY (a diferencia de RESTClient del SDK oficial, que usa
    urllib3.PoolManager y se cuelga detrás de un proxy corporativo)."""
    params["apiKey"] = polygon_api_key
    response = requests.get(f"{POLYGON_BASE_URL}{path}", params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def is_market_open() -> bool:
    data = _polygon_get("/v1/marketstatus/now")
    return data.get("market") == "open"


def get_all_share_prices_polygon_eod() -> dict[str, float]:
    """Con mucho agradecimiento a la estudiante Reema R. por arreglar el problema de la zona horaria en esto!"""
    probe = _polygon_get("/v2/aggs/ticker/SPY/prev")["results"][0]
    last_close = datetime.fromtimestamp(probe["t"] / 1000, tz=timezone.utc).date()

    data = _polygon_get(
        f"/v2/aggs/grouped/locale/us/market/stocks/{last_close}",
        adjusted="true",
        include_otc="false",
    )
    return {result["T"]: result["c"] for result in data.get("results", [])}


@lru_cache(maxsize=2)
def get_market_for_prior_date(today):
    market_data = read_market(today)
    if not market_data:
        market_data = get_all_share_prices_polygon_eod()
        write_market(today, market_data)
    return market_data


def get_share_price_polygon_eod(symbol) -> float:
    today = datetime.now().date().strftime("%Y-%m-%d")
    market_data = get_market_for_prior_date(today)
    return market_data.get(symbol, 0.0)


def get_share_price_polygon_min(symbol) -> float:
    data = _polygon_get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
    ticker = data.get("ticker") or {}
    min_close = (ticker.get("min") or {}).get("c")
    prev_close = (ticker.get("prevDay") or {}).get("c")
    return min_close or prev_close or 0.0


def get_share_price_polygon(symbol) -> float:
    if is_paid_polygon:
        return get_share_price_polygon_min(symbol)
    else:
        return get_share_price_polygon_eod(symbol)


def get_share_price(symbol) -> float:
    if polygon_api_key:
        try:
            return get_share_price_polygon(symbol)
        except Exception as e:
            print(f"No se pudo usar la API de Polygon debido a {e}; usando un número aleatorio")
    return float(random.randint(1, 100))
