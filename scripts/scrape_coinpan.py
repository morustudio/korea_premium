import json
import os
import re
from datetime import datetime, timezone, timedelta

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

KST = timezone(timedelta(hours=9))
URL = "https://coinpan.com/"


def parse_premium_text(td_text: str) -> int | None:
    """
    Examples:
      "+587,305 +0.44%" -> 587305
      "-”               -> None
    """
    td_text = td_text.strip()
    if td_text == "-" or td_text == "":
        return None

    # 숫자(콤마 포함)만 잡아서 int로
    m = re.search(r"([+-]?\d[\d,]*)", td_text)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def fetch_html_playwright() -> str:
    """
    coinpan은 requests로 가져오면 값이 비어있거나 차단될 수 있어,
    브라우저 렌더링 후 최종 HTML을 얻는다.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
        )

        page.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # 테이블이 존재할 때까지 대기
        page.wait_for_selector("table.coin_currency", timeout=60000)

        # JS로 숫자 채워질 시간을 조금 더 줌
        page.wait_for_timeout(3000)

        html = page.content()
        browser.close()
        return html


def extract_premiums(html: str) -> dict[str, int | None]:
    soup = BeautifulSoup(html, "html.parser")

    table = soup.select_one("table.coin_currency")
    if not table:
        raise RuntimeError("coin_currency table not found (blocked or page changed)")

    out: dict[str, int | None] = {}
    rows = table.select("tbody tr.exchange_info")
    if not rows:
        raise RuntimeError("exchange rows not found (blocked or page changed)")

    for row in rows:
        ex_key = row.get("data-exchange")
        if not ex_key:
            # fallback: exchange name text
            th = row.select_one("th.exchange_name")
            ex_key = th.get_text(strip=True) if th else "unknown"

        td = row.select_one("td.price.korea_premium")
        if not td:
            # 어떤 행은 없을 수도 있음
            out[ex_key] = None
            continue

        premium_value = parse_premium_text(td.get_text(" ", strip=True))
        out[ex_key] = premium_value

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
    today = datetime.now(KST).strftime("%Y-%m-%d")

    html = fetch_html_playwright()

    # ✅ 디버그: Actions에서 확인 가능하도록 저장
    with open("coinpan_debug.html", "w", encoding="utf-8") as f:
        f.write(html)

    premiums = extract_premiums(html)

    # 값이 전부 None이면 실패로 보고 에러를 던져서 Actions에서 바로 감지되게 함
    if premiums and all(v is None for v in premiums.values()):
        raise RuntimeError("All premiums are None (likely still blocked or values not rendered)")

    path = "data/korea_premium.json"
    rows = load_json(path)

    # 같은 날짜 데이터가 있으면 덮어쓰기(재실행 대비)
    rows = [r for r in rows if r.get("date"]()
