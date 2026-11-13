"""E：決定要抓哪些資料，依序執行，存成 raw。

    uv run python -m crawler.extract_raw                        # 抓今天（daily ＝ 只有今天的 init）
    uv run python -m crawler.extract_raw init --start 20261001  # 回補到今天（可加 --end、--refetch）
    uv run python -m crawler.extract_raw daily --source twse    # 只跑證交所（mops：只跑觀測站）

重大訊息規則見 build_mops_jobs。
"""
import argparse
import datetime
import time

import pandas as pd

from crawler import raw_file
from crawler import tasks_crawler_mops as mops
from crawler import tasks_crawler_twse as twse
from crawler.config import SLEEP_SECONDS, SLEEP_SECONDS_MOPS
from crawler.date_utils import month_end, prev_month, today_yyyymmdd


# ---------- 第一批：證交所 ----------
def build_twse_jobs(start: str, end: str) -> list[tuple]:
    """回傳 [(任務函式, 參數), ...]。"""
    days = pd.date_range(start, end).strftime("%Y%m%d").tolist()
    months = pd.period_range(pd.Timestamp(start), pd.Timestamp(end), freq="M").strftime("%Y%m").tolist()
    years = sorted({int(m[:4]) for m in months})

    this_year = int(today_yyyymmdd()[:4])
    jobs = [(twse.crawler_holiday, (y,)) for y in years
            if y >= this_year or not raw_file.raw_path("holiday", str(y)).exists()]   # 過去的年份不會再變，有檔就跳過
    jobs += [(twse.crawler_market_daily, (m,)) for m in months]
    jobs += [(twse.crawler_notice, (d,)) for d in days]
    jobs += [(twse.crawler_punish, (d,)) for d in days]
    jobs += [(twse.crawler_companies, ())]              # 查重大訊息前要先有公司清單
    if end == today_yyyymmdd():
        jobs += [(twse.crawler_punish_watchlist, ())]   # 只有最新一天，回補時抓不到舊的
    return jobs


# ---------- 第二批：觀測站重大訊息（要先有第一批的注意股、處置股、公司清單）----------
def company_ids() -> set[str]:
    """最新一份上市公司清單的代號。"""
    latest = raw_file.list_raw("companies")[-1]
    return {c["公司代號"].strip() for c in raw_file.load_raw("companies", latest)["body"]}


def watched_stocks(yyyymmdd: str) -> set[str]:
    """某一天的關注名單：當天被列注意的股票＋處置中的股票。"""
    notice = raw_file.load_raw("notice", yyyymmdd)
    punish = raw_file.load_raw("punish", yyyymmdd)   # 含當天起 14 天內處置中的公告
    ids = {row[1] for row in (notice["body"].get("data") or [])} if notice else set()
    ids |= {row[2] for row in (punish["body"].get("data") or [])} if punish else set()
    return {i.strip() for i in ids}


def is_complete(stock_id: str, yyyymm: str) -> bool:
    """月底之後才抓的才算完整（月中抓的只查到當天）。"""
    raw = raw_file.load_raw("announcements", f"{stock_id}_{yyyymm}")
    if raw is None:
        return False
    return datetime.datetime.fromisoformat(raw["meta"]["fetched_at"]).date() > month_end(yyyymm)


def announcement_job(stock_id: str, yyyymm: str) -> tuple:
    return (mops.crawler_announcements, (stock_id, int(yyyymm[:4]), int(yyyymm[4:])))


def last_month_gaps(this_month: str, companies: set[str]) -> set[tuple[str, str]]:
    """上個月被關注過的上市公司，上個月的重大訊息不完整（或沒有）就補。名單取自 raw，不連資料庫。"""
    yyyymm = prev_month(this_month)
    days = pd.date_range(f"{yyyymm}01", month_end(yyyymm)).strftime("%Y%m%d")
    watched = set().union(*(watched_stocks(d) for d in days)) & companies
    return {(s, yyyymm) for s in watched if not is_complete(s, yyyymm)}


def build_mops_jobs(start: str, end: str, refetch: bool = False) -> list[tuple]:
    """關注中上市公司的當月＋上個月重大訊息（要先抓完注意股、處置股）。

    當月每次重抓；過去的月份沒有完整檔才抓（refetch 則全抓）；另補上個月的缺口。
    """
    companies = company_ids()
    this_month = today_yyyymmdd()[:6]
    targets = set()
    for yyyymmdd in pd.date_range(start, end).strftime("%Y%m%d"):
        for stock_id in watched_stocks(yyyymmdd) & companies:   # 權證、ETF 沒有重大訊息
            for yyyymm in (yyyymmdd[:6], prev_month(yyyymmdd)):
                if yyyymm <= this_month:
                    targets.add((stock_id, yyyymm))
    if not refetch:
        targets = {(s, m) for s, m in targets if m == this_month or not is_complete(s, m)}
    targets |= last_month_gaps(this_month, companies)
    return [announcement_job(s, m) for s, m in sorted(targets)]


# ---------- 執行 ----------
def run_jobs(jobs: list[tuple], sleep: float) -> list[str]:
    """依序執行，回傳失敗的任務。單一任務失敗不會中斷整批。

    jobs 例如 [(crawler_notice, ("20261113",)), (crawler_announcements, ("2330", 2026, 11))]
    """
    failed = []
    for func, args in jobs:
        name = f"{func.__name__}{args}"          # log 用，例如 crawler_notice('20261113',)
        try:
            path = func(*args)                   # 執行任務：打 API、存檔，回傳檔案路徑（*args 拆開傳入）
            filename = path.name                 # 從路徑取出檔名
            print(name, "→", filename)           # 印到 log
        except Exception as e:                   # 被擋、逾時等：記下來，繼續下一個
            print(name, "✗", e)
            failed.append(name)
        time.sleep(sleep)                        # 間隔一下，避免被擋
    return failed


def parse_args() -> argparse.Namespace:
    """讀指令參數，例如 `init --start 20261001` → args.mode="init"、args.start="20261001"。"""
    common = argparse.ArgumentParser(add_help=False)          # 兩個模式共用的參數
    common.add_argument("--source", choices=["all", "twse", "mops"], default="all",
                        help="只跑證交所或觀測站（Airflow 分任務用），預設都跑")
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode")                # 模式（子指令）存到 args.mode；沒給就是 None
    sub.add_parser("daily", parents=[common], help="只抓今天（預設）")                 # 模式 daily
    init = sub.add_parser("init", parents=[common], help="回補一段期間")              # 模式 init：另加 3 個參數
    init.add_argument("--start", required=True, help="YYYYMMDD")                     # 必填
    init.add_argument("--end", default=today_yyyymmdd(), help="YYYYMMDD，預設今天")    # 沒給就用今天
    init.add_argument("--refetch", action="store_true", help="重大訊息已有完整檔也重抓")  # 開關：有寫就是 True
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "init":
        start, end, refetch = args.start, args.end, args.refetch
    else:
        start = end = today_yyyymmdd()
        refetch = False
    source = getattr(args, "source", "all")   # 什麼模式都沒給時沒有 source

    failed = []
    if source in ("all", "twse"):
        failed += run_jobs(build_twse_jobs(start, end), SLEEP_SECONDS)
    if source in ("all", "mops"):   # 要先有證交所的注意股、處置股、公司清單
        failed += run_jobs(build_mops_jobs(start, end, refetch), SLEEP_SECONDS_MOPS)

    print("\n失敗：", failed or "無")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
