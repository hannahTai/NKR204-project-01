"""派工層（producer）：只負責「決定這一輪要做哪些任務」，再依序送出。

它不知道抓資料要呼叫哪個 API，也不知道資料會被存到哪裡。

    uv run python -m crawler.producer                       # 每日：今天
    uv run python -m crawler.producer --start 20261001      # 回補：20261001 到今天
    uv run python -m crawler.producer --start 20261001 --end 20261031

每日 = 回補一天：同一套 build_jobs()，只差日期範圍。
範圍包含今天時，才加上「沒有歷史、只能存當下」的兩顆任務（注意累計名單、上市公司基本資料）。

此時任務是直接呼叫函式、循序執行；接 Celery 時，只要把 run_jobs() 裡的
job["task"](**job["kwargs"]) 換成 job["task"].delay(**job["kwargs"])。
"""
import argparse
import re
import time
from datetime import date

from crawler import repository, task
from crawler.config import SLEEP_SECONDS, SLEEP_SECONDS_MOPS
from crawler.date_utils import DATE_FMT, date_range, month_range, prev_month


def build_jobs(start: str, end: str) -> list[dict]:
    """產生這一輪的任務清單（公司重大訊息除外，見 build_announcement_jobs）。

    每個元素：{"task": 任務函式, "kwargs": 參數}。
    任務顆粒度在這裡決定，task.py 不用動。
    """
    days = date_range(start, end)
    months = month_range(start, end)
    years = sorted({int(m[:4]) for m in months})

    jobs = (
        [{"task": task.crawl_holiday, "kwargs": {"year": y}} for y in years]      # 一年一次
        + [{"task": task.crawl_fmtqik, "kwargs": {"month": m}} for m in months]  # 一月一次（交易日曆）
        + [{"task": task.crawl_notice, "kwargs": {"date": d}} for d in days]     # 一天一次
        + [{"task": task.crawl_punish, "kwargs": {"date": d}} for d in days]     # 一天一次
    )
    if end == date.today().strftime(DATE_FMT):
        # 沒有歷史的：只有「今天」有意義
        jobs += [{"task": task.crawl_notetrans, "kwargs": {}},
                 {"task": task.crawl_companies, "kwargs": {}}]
    return jobs


def build_announcement_jobs(start: str, end: str) -> list[dict]:
    """公司重大訊息的任務清單：從已存的注意股 raw 推出要查哪些公司、哪幾個月。

    必須等注意股抓完才能產生，所以和 build_jobs() 分開。
    - 只取 4 碼數字的代號，先排除 6 碼的權證；
      但 DR（例如 9103）也是 4 碼，會漏網，多打幾個請求而已。
      精確的判斷（比對上市公司清單）等 stage 層做好再換
    - 月份 = 被列注意的那個月＋前一個月（公告 tag 看最近 30 個營業日，可能跨月）
    - 不抓未來的月份
    """
    this_month = date.today().strftime("%Y%m")
    targets = set()
    for d in date_range(start, end):
        envelope = repository.load_raw("twse_notice", d)
        for row in (envelope or {}).get("body", {}).get("data") or []:
            code = row[1]   # 欄位順序：編號、證券代號、證券名稱、…
            if re.fullmatch(r"\d{4}", code):
                for month in (d[:6], prev_month(d[:6])):
                    if month <= this_month:
                        targets.add((code, int(month[:4]), int(month[4:])))
    return [{"task": task.crawl_announcements,
             "kwargs": {"stock_id": code, "year": y, "month": m}}
            for code, y, m in sorted(targets)]


def run_jobs(jobs: list[dict], sleep: float) -> list[str]:
    """依序執行任務，回傳失敗的任務名稱。某顆失敗不會中斷整批。"""
    failed = []
    for job in jobs:
        name = f"{job['task'].__name__}({', '.join(map(str, job['kwargs'].values()))})"
        try:
            print(name, "→", job["task"](**job["kwargs"]).name)
        except Exception as e:
            print(name, "✗", e)
            failed.append(name)
        time.sleep(sleep)   # 間隔一下，太快會被擋
    return failed


def main() -> None:
    today = date.today().strftime(DATE_FMT)
    parser = argparse.ArgumentParser(description="抓資料存成 raw（每日或回補）")
    parser.add_argument("--start", default=today, help="起始日 YYYYMMDD（預設今天）")
    parser.add_argument("--end", default=today, help="結束日 YYYYMMDD，含當天（預設今天）")
    args = parser.parse_args()

    failed = run_jobs(build_jobs(args.start, args.end), SLEEP_SECONDS)
    failed += run_jobs(build_announcement_jobs(args.start, args.end), SLEEP_SECONDS_MOPS)

    print("\n失敗：", failed or "無")
    if failed:
        raise SystemExit(1)   # 結束碼 1：讓排程工具知道這次沒成功


if __name__ == "__main__":
    main()
