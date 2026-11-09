"""任務：一次抓一份資料存成 raw，回傳檔案路徑。"""
import re
from pathlib import Path

from crawler import client, repository
from crawler.date_utils import DATE_FMT, roc_to_date, today_key


def crawl_notice(day: str) -> Path:
    return repository.save_raw_response("notice", day, client.fetch_notice(day))


def crawl_punish(day: str) -> Path:
    return repository.save_raw_response("punish", day, client.fetch_punish(day))


def crawl_holiday(year: int) -> Path:
    return repository.save_raw_response("holiday", str(year), client.fetch_holiday(year))


def crawl_market_daily(month: str) -> Path:
    return repository.save_raw_response("market_daily", month, client.fetch_market_daily(month))


def crawl_punish_watchlist() -> Path:
    """檔名用名單上的資料日期（週末抓到的是週五的名單）。"""
    resp = client.fetch_punish_watchlist()
    body = repository.parse_body(resp)
    title = body.get("title", "") if isinstance(body, dict) else ""
    found = re.search(r"\d+年\d+月\d+日", title)
    key = roc_to_date(found.group()).strftime(DATE_FMT) if found else today_key()
    return repository.save_raw_response("punish_watchlist", key, resp)


def crawl_companies() -> Path:
    """檔名用抓取日期（每天一份快照）。"""
    return repository.save_raw_response("companies", today_key(), client.fetch_companies())


def crawl_announcements(stock_id: str, year: int, month: int) -> Path:
    resp = client.fetch_announcements(stock_id, year, month)
    return repository.save_raw_response("announcements", f"{stock_id}_{year:04d}{month:02d}", resp)
