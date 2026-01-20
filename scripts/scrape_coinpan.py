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


def safe_int(x) -> int | None:
    try:
        if x is None:
            return None
        if isinstance(x, str):
            x = x.replace(",", "").strip()
        return int(float(x))
    except Exception:
        return None


# --------------------------
# FX: USD -> KRW (무료/무키)
# --------------------------
def fetch_usdkrw() -> float:
    """
    무료 환율 API (키 없이 동작하는 편)
    실패 시 예외 발생 -> 상위에서 처리
    """
    j = get_json("https://open.er-api.com/v6/latest/USD")
    rate = j["rates"]["KRW"]
    return float(rate)


# --------------------------
# Global BTC/USD proxy
# --------------------------
def fetch_global_btc_usd() -> float:
    """
    해외 BTC 가격(USD 대용): Binance BTCUSDT 사용 (USDT≈USD 가정)
    """
    j = get_json("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
    return float(j["price"])


# --------------------------
# Domestic BTC/KRW
# --------------------------
def fetch_upbit_btc_krw() -> int:
    j = get_json("https://api.upbit.com/v1/ticker?markets=KRW-BTC")
    return safe_int(j[0]["trade_price"])


def fetch_bithumb_btc_krw() -> int:
    j = get_json("https://api.bithumb.com/public/ticker/BTC_KRW")
    # closing_price가 문자열로 옴
    return safe_int(j["data"]["closing_price"])


def fetch_coinone_btc_krw() -> int:
    j = get_json("https://api.coinone.co.kr/public/v2/ticker_new/KRW/BTC")
    # last가 문자열
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

    # 1) 환율/해외가격
    usdkrw = fetch_usdkrw()
    global_usd = fetch_global_btc_usd()
    global_krw = global_usd * usdkrw

    # 2) 국내가격
    # (실패해도 다른 거래소는 계속 저장되도록 try)
    premiums: dict[str, int | None] = {}

    def put(name: str, fn):
        try:
            domestic = fn()
            premium = domestic - global_krw
            premiums[name] = int(round(premium))
        except Exception:
            premiums[name] = None

    put("bithumb", fetch_bithumb_btc_krw)
    put("upbit", fetch_upbit_btc_krw)
    put("coinone", fetch_coinone_btc_krw)
    put("korbit", fetch_korbit_btc_krw)

    # 참고용으로 글로벌 기준값도 저장(차트/디버깅에 유용)
    meta = {
        "usdkrw": usdkrw,
        "global_btc_usd": global_usd,
        "global_btc_krw": global_krw,
        "global_source": "binance_BTCUSDT + USDKRW",
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
