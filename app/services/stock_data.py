import asyncio
import time
from functools import partial
from typing import Optional

from curl_cffi import requests as cffi_requests

_name_cache: dict[str, str] = {}
EASTMONEY_PUSH_URL = "https://push2.eastmoney.com/api/qt/stock/get"
EASTMONEY_FIELDS = "f43,f57,f58,f170"

_US_EXCHANGES = [105, 106, 107]


def _cn_exchange_code(ticker: str) -> int:
    """Determine SH(1) vs SZ(0) from A-share ticker prefix."""
    if ticker.startswith("6"):
        return 1
    return 0


def _fetch_eastmoney_quote(secid: str) -> Optional[dict]:
    try:
        r = cffi_requests.get(
            EASTMONEY_PUSH_URL,
            params={"secid": secid, "fields": EASTMONEY_FIELDS},
            impersonate="chrome",
            timeout=10,
        )
        data = r.json().get("data")
        if not data or data.get("f58") is None:
            return None
        raw_price = data.get("f43", 0)
        raw_change = data.get("f170")
        if raw_price in ("-", None):
            return None
        return {
            "name": str(data["f58"]),
            "price": int(raw_price) / 1000,
            "change_pct": int(raw_change) / 100 if raw_change not in (None, "-") else None,
        }
    except Exception:
        return None


def _lookup_cn(ticker: str) -> Optional[dict]:
    """Lookup a CN A-share stock using akshare, then East Money as fallback."""
    try:
        import akshare as ak

        df = ak.stock_individual_info_em(symbol=ticker)
        info = dict(zip(df["item"], df["value"]))
        name = str(info.get("股票简称", ticker))
        price = float(info.get("最新", 0))
        _name_cache[f"cn:{ticker}"] = name
        return {
            "ticker": ticker,
            "market": "cn",
            "company_name": name,
            "current_price": price,
            "price_change_pct": None,
        }
    except Exception:
        pass

    exchange = _cn_exchange_code(ticker)
    result = _fetch_eastmoney_quote(f"{exchange}.{ticker}")
    if result:
        _name_cache[f"cn:{ticker}"] = result["name"]
        return {
            "ticker": ticker,
            "market": "cn",
            "company_name": result["name"],
            "current_price": result["price"],
            "price_change_pct": result["change_pct"],
        }
    return None


def _lookup_us(ticker: str) -> Optional[dict]:
    """Lookup a US stock by trying NASDAQ / NYSE / AMEX exchange codes."""
    ticker = ticker.upper()
    for ex in _US_EXCHANGES:
        result = _fetch_eastmoney_quote(f"{ex}.{ticker}")
        if result and result["price"] > 0:
            _name_cache[f"us:{ticker}"] = result["name"]
            return {
                "ticker": ticker,
                "market": "us",
                "company_name": result["name"],
                "current_price": result["price"],
                "price_change_pct": result["change_pct"],
            }

    # Fallback: use akshare stock_us_daily for price (no company name)
    try:
        import akshare as ak

        df = ak.stock_us_daily(symbol=ticker)
        if df is not None and not df.empty:
            last = df.iloc[-1]
            name = _name_cache.get(f"us:{ticker}", ticker)
            return {
                "ticker": ticker,
                "market": "us",
                "company_name": name,
                "current_price": float(last["close"]),
                "price_change_pct": None,
            }
    except Exception:
        pass
    return None


def _lookup_hk(ticker: str) -> Optional[dict]:
    """Lookup a HK stock via East Money, then akshare as fallback."""
    result = _fetch_eastmoney_quote(f"116.{ticker}")
    if result and result["price"] > 0:
        _name_cache[f"hk:{ticker}"] = result["name"]
        return {
            "ticker": ticker,
            "market": "hk",
            "company_name": result["name"],
            "current_price": result["price"],
            "price_change_pct": result["change_pct"],
        }

    try:
        import akshare as ak

        name = _name_cache.get(f"hk:{ticker}", ticker)
        try:
            profile = ak.stock_hk_company_profile_em(symbol=ticker)
            if not profile.empty:
                name = str(profile.iloc[0]["公司名称"])
                _name_cache[f"hk:{ticker}"] = name
        except Exception:
            pass

        df = ak.stock_hk_daily(symbol=ticker)
        if df is not None and not df.empty:
            price = float(df.iloc[-1]["close"])
            return {
                "ticker": ticker,
                "market": "hk",
                "company_name": name,
                "current_price": price,
                "price_change_pct": None,
            }
    except Exception:
        pass
    return None


_LOOKUP_FNS = {"cn": _lookup_cn, "us": _lookup_us, "hk": _lookup_hk}


def _lookup_sync(ticker: str, market: str) -> Optional[dict]:
    fn = _LOOKUP_FNS.get(market)
    if fn is None:
        raise ValueError(f"Unsupported market: {market}")
    return fn(ticker)


async def lookup_ticker(ticker: str, market: str) -> Optional[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_lookup_sync, ticker, market))


def _refresh_sync(records: list[dict]) -> dict[str, dict]:
    """Refresh prices for a list of records by looking up each stock individually."""
    results: dict[str, dict] = {}
    for rec in records:
        market = rec["market"]
        ticker = rec["ticker"]
        data = _lookup_sync(ticker, market)
        if data:
            results[f"{market}:{ticker}"] = {
                "current_price": data["current_price"],
                "price_change_pct": data.get("price_change_pct"),
            }
        time.sleep(0.1)
    return results


async def refresh_prices(records: list[dict]) -> dict[str, dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(_refresh_sync, records))
