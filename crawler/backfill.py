"""回補「有歷史可查」的資料源：uv run python -m crawler.backfill

沒有歷史的（注意累計名單、上市公司基本資料）不在這裡，見 daily.py。
每日排程也是呼叫這裡的 run()，只是範圍只有今天。
過渡用工具：接上 Airflow 之後，排程與回補改由 Airflow 處理。
"""
import re
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

from crawler.extract.mops import extract_announcements
from crawler.extract.twse import (
    extract_fmtqik, extract_holiday, extract_notice, extract_punish,
)
from crawler.storage.raw import load_raw
from crawler.utils.dates import date_range, month_range, prev_month


def backfill(extract: Callable, keys: list, sleep: float = 1.0) -> list:
    """對每個 key 呼叫 extract，回傳失敗的 key。某個失敗不會中斷整批。"""
    failed = []
    for key in keys:
        try:
            print(key, "→", extract(key).name)
        except Exception as e:
            print(key, "✗", e)
            failed.append(key)
        time.sleep(sleep)   # 間隔一下，太快會被擋
    return failed


def announcement_targets(days: list[str]) -> list[tuple[str, int, int]]:
    """要抓公告的（證券代號, 年, 月）：從已存的注意股 raw 檔推出來。

    - 只取 4 碼數字的代號，先排除 6 碼的權證；
      但 DR（例如 9103）也是 4 碼，會漏網，多打幾個請求而已。
      精確的判斷（比對上市公司清單）等解析層做好再換
    - 月份 = 被列注意的那個月＋前一個月（公告 tag 看最近 30 個營業日，可能跨月）
    - 不抓未來的月份
    """
    this_month = date.today().strftime("%Y%m")
    targets = set()
    for d in days:
        envelope = load_raw("twse_notice", d)
        for row in (envelope or {}).get("body", {}).get("data") or []:
            code = row[1]   # 欄位順序：編號、證券代號、證券名稱、…
            if re.fullmatch(r"\d{4}", code):
                for month in (d[:6], prev_month(d[:6])):
                    if month <= this_month:
                        targets.add((code, int(month[:4]), int(month[4:])))
    return sorted(targets)


def run(start: str, end: str) -> list:
    """抓 start 到 end（YYYYMMDD）之間所有「有歷史」的資料源，回傳失敗的 key。

    回補：run("20261001", 今天)
    每日：run(今天, 今天) → 同一套程式，只差日期範圍（每日 = 回補一天）
    """
    days = date_range(start, end)
    months = month_range(start, end)
    years = sorted({int(m[:4]) for m in months})

    failed = []

    # 有參數的：一個 key 一個請求
    for name, extract, keys in [
        ("開休市日期", extract_holiday, years),    # 一年一次
        ("市場成交", extract_fmtqik, months),      # 一月一次（交易日曆）
        ("注意股", extract_notice, days),          # 一天一次
        ("處置股", extract_punish, days),          # 一天一次
    ]:
        print(f"===== {name}")
        failed += backfill(extract, keys)

    # 公告：要先有注意股才知道查哪些公司，所以排最後；一次要帶 3 個參數
    print("===== 公司重大訊息")
    failed += backfill(lambda t: extract_announcements(*t),
                       announcement_targets(days), sleep=0.6)
    return failed


if __name__ == "__main__":
    failed = run("20261001", date.today().strftime("%Y%m%d"))
    print("\n失敗：", failed or "無")
