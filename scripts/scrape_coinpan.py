import json
import os
import re
import traceback
from datetime import datetime, timezone, timedelta

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

KST = timezone(timedelta(hours=9))
URL = "https://coinpan.com/"

DEBUG_HTML = "coinpan_debug.html"
DEBUG_SCREENSHOT = "coinpan_debug.png"
DEBUG_ERROR = "coinpan_error.txt"


def parse_premium_text(td_text: str) -> int | None:
    td_text = td_text.strip()
    if td_text == "-" or td_text == "":
        return None

    m = re.search(r"([+-]?\d[\d,]*)", td_text)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def fetch_html_playwright() -> str:
    """
    - 성공/실패 상관없이 디버그 파일을 최대한 남김
    - 실패 시에도 에러 로그, 스크린샷, (가능하면) HTML 저장
    """
    html = ""
    os.makedirs(".", exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            # 테이블이 나타날 때까지 대기 (JS 렌더링/지연 대비)
            page.wait_for_selector("table.coin_currency", timeout=60000)

            # 값 채우는 시간이 추가로 필요할 수 있어 조금 더 기다림
            page.wait_for_timeout(3000)

            html = page.content()
            return html

        except Exception:
            # 실패해도 최대한 자료 남기기
            try:
                page.screenshot(path=DEBUG_SCREENSHOT, full_page=True)
            except Exception:
                pass

            try:
                html = page.content()
            except Exception:
                html = ""

            with open(DEBUG_ERROR, "w", encoding="utf-8") as f:
                f.write("Playwright fetch failed.\n\n")
                f.write(traceback.format_exc())

            # html이 조금이라도 있으면 저장
            if html:
                with open(DEBUG_HTML, "w", encoding="utf-8") as f:
                    f.write(html)

            # 예외 다시 던져서 Actions에서 실패로 감지되게 함
            raise

        finally:
            try:
                browser.close()
            except Exception:
                pass


def extract_premiums(html: str) -> dict[str, int | None]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.coin_currency")
    if not table:
        raise RuntimeError("coin_currency table not found (blocked or page changed)")

    rows = table.select("tbody tr.exchange_info")
    if not rows:
        raise RuntimeError("exchange rows not found (blocked or page changed)")

    out: dict[str, int | None] = {}
    for row in rows:
        ex_key = row.get("data-exchange") or "unknown"
        td = row.select_one("td.price.korea_premium")
        if not td:
            out[ex_key] = None
            continue
        out[ex_key] = parse_premium_text(td.get_text(" ", strip=True))

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

    # ✅ 성공 경로에서도 디버그 HTML 저장
    with open(DEBUG_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    premiums = extract_premiums(html)

    # 값이 전부 None이면 “정상 수집 실패”로 처리해서 원인 추적하게 함
    if premiums and all(v is None for v in premiums.values()):
        with open(DEBUG_ERROR, "w", encoding="utf-8") as f:
            f.write("All premiums are None. Likely blocked or values not rendered.\n")
        raise RuntimeError("All premiums are None (blocked or not rendered)")

    path = "data/korea_premium.json"
    rows = load_json(path)

    rows = [r for r in rows if r.get("date") != today]
    rows.append({"date": today, "premiums": premiums})
    rows.sort(key=lambda x: x["date"])

    save_json(path, rows)
    print(f"Saved {today}: {premiums}")


if __name__ == "__main__":
    main()
