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
    v = safe_float(x)
    if v is None:
        return None
    return int(round(v))


# --------------------------
# FX: USD -> KRW (무료/무키)
# --------------------------
def fetch_usdkrw() -> float:
    """
    무료 환율 API (키 없음)
    """
    j = get_json("https://open.er-api.com/v6/latest/USD")
    rate = j["rates"]["KRW"]
    return float(rate)


# --------------------------
# Global BTC/USD (바이낸스 차단(451) 대비)
# 우선순위: CoinGecko -> Coinbase -> Kraken
# --------------------------
def fetch_global_btc_usd() -> tuple[float, str]:
    # 1) CoinGecko
    try:
        j = get_json("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd")
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

    # 1) 글로벌 기준(USD) + 환율
    usdkrw = fetch_usdkrw()
    global_usd, global_src = fetch_global_btc_usd()
    global_krw = global_usd * usdkrw

    # 2) 거래소별 김프(원/%) 계산
    premiums: dict[str, dict[str, int | float] | None] = {}

    def put(name: str, fn):
        try:
            domestic = fn()  # KRW
            if domestic is None:
                premiums[name] = None
                return

            diff_krw = domestic - global_krw
            diff_pct = (domestic / global_krw - 1.0) * 100.0

            premiums[name] = {
                "krw": int(round(diff_krw)),
                "pct": round(diff_pct, 4),  # 소수 4자리 (원하면 2자리로)
            }
        except Exception:
            premiums[name] = None

    put("bithumb", fetch_bithumb_btc_krw)
    put("upbit", fetch_upbit_btc_krw)
    put("coinone", fetch_coinone_btc_krw)
    put("korbit", fetch_korbit_btc_krw)

    # 3) 메타(디버깅/검증용)
    meta = {
        "usdkrw": usdkrw,
        "global_btc_usd": global_usd,
        "global_btc_krw": global_krw,
        "global_source": global_src,
        "note_pct": "premium_pct = (domestic_krw / (global_usd*usdkrw) - 1) * 100",
        "note_krw": "premium_krw = domestic_krw - (global_usd*usdkrw)",
    }

    # 4) JSON 누적 저장(동일 날짜는 덮어쓰기)
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
