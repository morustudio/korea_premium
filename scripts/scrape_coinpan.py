import json
import os
from datetime import datetime, timezone, timedelta

import requests

KST = timezone(timedelta(hours=9))
DATA_PATH = "data/korea_premium.json"


def get_json(url: str, headers: dict | None = None, timeout: int = 20) -> dict:
    r = requests.get(url, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def safe_float(x) -> float | None:
    try:
        if x is None:
            return None
        if isinstance(x, str):
            x = x.replace(",", "").strip()
        return float(x)
    except Exception:
        return None


def safe_int(x) -> int | None:
    try:
        v = safe_float(x)
        return None if v is None else int(round(v))
    except Exception:
        return None


# --------------------------
# FX: USD -> KRW (무료/무키)
# --------------------------
def fetch_usdkrw() -> float:
    j = get_json("https://open.er-api.com/v6/latest/USD")
    rate = j["rates"]["KRW"]
    return float(rate)


# --------------------------
# Global BTC/USD (바이낸스 금지 회피)
# 우선순위: CoinGecko -> Coinbase -> Kraken
# --------------------------
def fetch_global_btc_usd() -> tuple[float, str]:
    # 1) CoinGecko
    try:
        j = get_json(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        )
        price = safe_float(j["bitcoin"]["usd"])
        if price:
            return price, "coingecko"
    except Exception:
        pass

    # 2) Coinbase
    try:
        j = get_json("https://api.coinbase.com/v2/prices/BTC-USD/spot")
        price = safe_float(j["data"]["amount"])
        if price:
            return price, "coinbase"
    except Exception:
        pass

    # 3) Kraken
    try:
        j = get_json("https://api.kraken.com/0/public/Ticker?pair=XBTUSD")
        # Kraken 응답은 키가 변동될 수 있어 result의 첫 키를 사용
        result = j.get("result", {})
        first_key = next(iter(result.keys()))
        price = safe_float(result[first_key]["c"][0])  # last trade closed
        if price:
            return price, "kraken"
    except Exception:
        pass

    raise RuntimeError("Failed to fetch global BTC/USD from all providers")


# --------------------------
# Domestic BTC/KRW
# --------------------------
def fetch_upbit_btc_krw() -> int:
    j = get_json("https://api.upbit.com/v1/ticker?markets=KRW-BTC")
    return safe_int(j[0]["trade_price"])


def fetch_bithumb_btc_krw() -> int:
    j = get_json("https://api.bithumb.com/public/ticker/BTC_KRW")
    return safe_int(j["data"]["closing_price"])


def fetch_coinone_btc_krw() -> int:
    j = get_json("https://api.coinone.co.kr/public/v2/ticker_new/KRW/BTC")
    return safe_int(j["tickers"][0]["last"])


def fetch_korbit_btc_krw() -> int:
    j = get_json("https://api.korbit.co.kr/v1/ticker/detailed?currency_pair=btc_krw")
    return safe_int(j["last"])


def load_rows(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_rows(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def main():
    today = datetime.now(KST).strftime("%Y-%m-%d")

    usdkrw = fetch_usdkrw()
    global_usd, global_src = fetch_global_btc_usd()
    global_krw = global_usd * usdkrw

    premiums: dict[str, int | None] = {}

    def put(name: str, fn):
        try:
            domestic = fn()
            premiums[name] = int(round(domestic - global_krw))
        except Exception:
            premiums[name] = None

    put("bithumb", fetch_bithumb_btc_krw)
    put("upbit", fetch_upbit_btc_krw)
    put("coinone", fetch_coinone_btc_krw)
    put("korbit", fetch_korbit_btc_krw)

    meta = {
        "usdkrw": usdkrw,
        "global_btc_usd": global_usd,
        "global_btc_krw": global_krw,
        "global_source": global_src,
        "note": "premium_krw = domestic_btc_krw - (global_btc_usd * usdkrw)",
    }

    rows = load_rows(DATA_PATH)
    rows = [r for r in rows if r.get("date") != today]
    rows.append({"date": today, "premiums": premiums, "meta": meta})
    rows.sort(key=lambda x: x["date"])

    save_rows(DATA_PATH, rows)
    print(f"Saved {today}")
    print("premiums:", premiums)
    print("meta:", meta)


if __name__ == "__main__":
    main()
