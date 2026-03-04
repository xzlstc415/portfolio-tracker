import asyncio
import time
from functools import partial
from typing import Optional

from curl_cffi import requests as cffi_requests

_name_cache: dict[str, str] = {}
_fx_cache: dict[str, tuple[float, float]] = {}  # pair -> (timestamp, rate)
FX_CACHE_TTL = 300  # 5 minutes

EASTMONEY_PUSH_URL = "https://push2.eastmoney.com/api/qt/stock/get"
EASTMONEY_FIELDS = "f43,f57,f58,f152,f170"

_US_EXCHANGES = [105, 106, 107]

MARKET_CURRENCY = {"us": "USD", "hk": "HKD", "cn": "CNY"}

_FALLBACK_RATES = {"USDCNY": 7.25, "USDHKD": 7.80}


def _fetch_fx_rate(pair: str) -> Optional[float]:
    """Fetch a single forex rate from East Money (e.g. pair='USDCNY')."""
    cached = _fx_cache.get(pair)
    now = time.time()
    if cached and (now - cached[0]) < FX_CACHE_TTL:
        return cached[1]

    secid = f"119.{pair}"
    try:
        r = cffi_requests.get(
            EASTMONEY_PUSH_URL,
            params={"secid": secid, "fields": "f43,f57,f58"},
            impersonate="chrome",
            timeout=10,
        )
        data = r.json().get("data")
        if data and data.get("f43") not in (None, "-"):
            rate = int(data["f43"]) / 10000
            _fx_cache[pair] = (now, rate)
            return rate
    except Exception:
        pass

    if cached:
        return cached[1]
    return _FALLBACK_RATES.get(pair)


def get_exchange_rates() -> dict[str, float]:
    """Return exchange rates needed to convert HKD and CNY to USD."""
    usdcny = _fetch_fx_rate("USDCNY") or _FALLBACK_RATES["USDCNY"]
    usdhkd = _fetch_fx_rate("USDHKD") or _FALLBACK_RATES["USDHKD"]
    return {"USDCNY": usdcny, "USDHKD": usdhkd}


def convert_to_usd(value: float, market: str, rates: dict[str, float]) -> float:
    """Convert a market-value in its native currency to USD."""
    if market == "us":
        return value
    if market == "cn":
        return value / rates["USDCNY"]
    if market == "hk":
        return value / rates["USDHKD"]
    return value


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
        decimals = data.get("f152", 2)
        divisor = 10 ** int(decimals)
        return {
            "name": str(data["f58"]),
            "price": int(raw_price) / divisor,
            "change_pct": int(raw_change) / 100 if raw_change not in (None, "-") else None,
        }
    except Exception:
        return None


def _fetch_sina_cn_quote(ticker: str) -> Optional[dict]:
    """Fetch a CN A-share quote from Sina Finance (independent of East Money)."""
    import requests

    prefix = "sh" if ticker.startswith("6") else "sz"
    try:
        r = requests.get(
            f"https://hq.sinajs.cn/list={prefix}{ticker}",
            headers={"Referer": "https://finance.sina.com.cn"},
            timeout=10,
        )
        text = r.text.strip()
        if '=""' in text or not text:
            return None
        csv = text.split('"')[1]
        fields = csv.split(",")
        if len(fields) < 4 or not fields[3]:
            return None
        name = fields[0]
        price = float(fields[3])
        prev_close = float(fields[2]) if fields[2] else None
        change_pct = None
        if prev_close and prev_close > 0:
            change_pct = round((price - prev_close) / prev_close * 100, 2)
        if price <= 0:
            return None
        return {
            "ticker": ticker,
            "market": "cn",
            "company_name": name,
            "current_price": price,
            "price_change_pct": change_pct,
        }
    except Exception:
        return None


def _lookup_cn(ticker: str) -> Optional[dict]:
    """Lookup a CN A-share stock via East Money, akshare, then Sina as fallback."""
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

    sina = _fetch_sina_cn_quote(ticker)
    if sina:
        _name_cache[f"cn:{ticker}"] = sina["company_name"]
        return sina

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
