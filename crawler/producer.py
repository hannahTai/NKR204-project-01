"""決定要抓哪些資料，依序執行。

    uv run python -m crawler.producer                    # 今天
    uv run python -m crawler.producer --start 20261001   # 20261001 到今天
"""
import argparse
import time

from crawler import repository, task
from crawler.config import SLEEP_SECONDS, SLEEP_SECONDS_MOPS
from crawler.date_utils import date_range, month_range, prev_month, today_key


def build_jobs(start: str, end: str) -> list[tuple]:
    """回傳 [(任務函式, 參數), ...]。"""
    days = date_range(start, end)
    months = month_range(start, end)
    years = sorted({int(m[:4]) for m in months})

    jobs = [(task.crawl_holiday, (y,)) for y in years]
    jobs += [(task.crawl_market_daily, (m,)) for m in months]
    jobs += [(task.crawl_notice, (d,)) for d in days]
    jobs += [(task.crawl_punish, (d,)) for d in days]
    jobs += [(task.crawl_companies, ())]              # 查重大訊息前要先有公司清單
    if end == today_key():
        jobs += [(task.crawl_punish_watchlist, ())]   # 只有最新一天，回補時抓不到舊的
    return jobs


def company_ids() -> set[str]:
    """最新一份上市公司清單的代號。"""
    latest = repository.list_raw("companies")[-1]
    return {c["公司代號"].strip() for c in repository.load_raw("companies", latest)["body"]}


def build_announcement_jobs(start: str, end: str) -> list[tuple]:
    """被列注意的上市公司，查當月與上個月的重大訊息（要先抓完注意股）。"""
    companies = company_ids()
    this_month = today_key()[:6]
    targets = set()
    for day in date_range(start, end):
        raw = repository.load_raw("notice", day)
        for row in (raw["body"].get("data") or []) if raw else []:
            stock_id = row[1].strip()
            if stock_id not in companies:   # 權證、ETF 沒有重大訊息
                continue
            for month in (day[:6], prev_month(day[:6])):
                if month <= this_month:
                    targets.add((stock_id, int(month[:4]), int(month[4:])))
    return [(task.crawl_announcements, t) for t in sorted(targets)]


def run_jobs(jobs: list[tuple], sleep: float) -> list[str]:
    """依序執行，回傳失敗的任務。單一任務失敗不會中斷整批。"""
    failed = []
    for func, args in jobs:
        name = f"{func.__name__}{args}"
        try:
            print(name, "→", func(*args).name)
        except Exception as e:
            print(name, "✗", e)
            failed.append(name)
        time.sleep(sleep)
    return failed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=today_key(), help="YYYYMMDD，預設今天")
    parser.add_argument("--end", default=today_key(), help="YYYYMMDD，預設今天")
    args = parser.parse_args()

    failed = run_jobs(build_jobs(args.start, args.end), SLEEP_SECONDS)
    failed += run_jobs(build_announcement_jobs(args.start, args.end), SLEEP_SECONDS_MOPS)

    print("\n失敗：", failed or "無")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
