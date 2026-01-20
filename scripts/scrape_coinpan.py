# scripts/scrape_coinpan.py
import json
import os
import re
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup


KST = timezone(timedelta(hours=9))
URL = "https://coinpan.com/"


def parse_premium_text(td_text: str) -> int | None:
    """
    Examples:
      "+587,305 +0.44%" -> 587305
      "-"              -> None
    """
    td_text = td_text.strip()
    if td_text == "-" or td_text == "":
        return None

    # 숫자(콤마 포함)만 잡아서 int로
    m = re.search(r"([+-]?\d[\d,]*)", td_text)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def fetch_html_requests() -> str:
    # 403 방지용 헤더(그래도 막힐 수 있음)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; premium-tracker/1.0; +https://github.com/)",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://coinpan.com/",
    }
    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def extract_premiums(html: str) -> dict[str, int | None]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.coin_currency")
    if not table:
        raise RuntimeError("coin_currency table not found")

    out: dict[str, int | None] = {}
    for row in table.select("tbody tr.exchange_info"):
        ex = row.get("data-exchange") or row.select_one("th.exchange_name")
        ex_name = ex if isinstance(ex, str) else ex.get_text(strip=True)

        td = row.select_one("td.price.korea_premium")
        if not td:
            continue
        premium_value = parse_premium_text(td.get_text(" ", strip=True))
        out[ex_name] = premium_value

    if not out:
        raise RuntimeError("No premiums extracted")
    return out


def load_json(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    # KST 날짜(일봉)
    today = datetime.now(KST).strftime("%Y-%m-%d")

    html = fetch_html_requests()
    premiums = extract_premiums(html)

    path = "data/korea_premium.json"
    rows = load_json(path)

    # 같은 날짜가 이미 있으면 덮어쓰기(재실행 대비)
    rows = [r for r in rows if r.get("date") != today]
    rows.append({"date": today, "premiums": premiums})
    rows.sort(key=lambda x: x["date"])

    save_json(path, rows)
    print(f"Saved {today}: {premiums}")


if __name__ == "__main__":
    main()
