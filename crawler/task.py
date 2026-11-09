"""任務層（task）：一次呼叫只處理「一顆任務」。

每顆任務：抓（client）→ 原樣存成 raw（repository）。
三個特徵讓它之後可以直接加上 @app.task 丟進 Celery：
    1. 所有輸入都由參數帶進來，函式內部沒有任何寫死的清單
    2. 不依賴其他任務的執行結果，單獨呼叫就能完成
    3. 結果直接寫進儲存層

只做「抓 → 存 raw」，不在這裡整理，整理拆到 stage.py。
因為整理一定會寫錯，raw 留著，改了整理規則直接重算，不必重抓。

| 任務 | raw 存在 data/raw/<source>/<key>.json |
|---|---|
| crawl_notice(date)          | twse_notice/YYYYMMDD |
| crawl_punish(date)          | twse_punish/YYYYMMDD |
| crawl_notetrans()           | twse_notetrans/YYYYMMDD（資料日期，取自回應） |
| crawl_holiday(year)         | twse_holiday/YYYY |
| crawl_fmtqik(month)         | twse_fmtqik/YYYYMM |
| crawl_companies()           | twse_t187ap03_L/YYYYMMDD（抓取日期） |
| crawl_announcements(...)    | mops_t05st01/<代號>_YYYYMM |
"""
import re
from datetime import date
from pathlib import Path

from crawler import client, repository
from crawler.date_utils import DATE_FMT, roc_to_date


def crawl_notice(date: str) -> Path:
    """某一天的注意股。沒開市的日子也照樣存（data 是空的）：
    存了才分得出「查過、確實沒資料」和「根本沒查」。"""
    return repository.save_raw_response("twse_notice", date, client.fetch_notice(date))


def crawl_punish(date: str) -> Path:
    """某一天的處置股。"""
    return repository.save_raw_response("twse_punish", date, client.fetch_punish(date))


def crawl_holiday(year: int) -> Path:
    """某一年的開休市日期。"""
    return repository.save_raw_response("twse_holiday", str(year), client.fetch_holiday(year))


def crawl_fmtqik(month: str) -> Path:
    """某個月的每日市場成交資訊（交易日曆）。"""
    return repository.save_raw_response("twse_fmtqik", month, client.fetch_fmtqik(month))


def crawl_notetrans() -> Path:
    """最新一日的注意累計名單。key 用回應裡的資料日期，不用抓取日期：
    週末抓到的是週五的名單，key 應該是週五。"""
    resp = client.fetch_notetrans()
    body = repository.parse_body(resp)
    title = body.get("title", "") if isinstance(body, dict) else ""
    m = re.search(r"\d+年\d+月\d+日", title)          # 例如「115年11月06日」
    key = roc_to_date(m.group()).strftime(DATE_FMT) if m else date.today().strftime(DATE_FMT)
    return repository.save_raw_response("twse_notetrans", key, resp)


def crawl_companies() -> Path:
    """上市公司基本資料的當日快照。key 用抓取日期：公司會上市、下市、改名。"""
    today = date.today().strftime(DATE_FMT)
    return repository.save_raw_response("twse_t187ap03_L", today, client.fetch_companies())


def crawl_announcements(stock_id: str, year: int, month: int) -> Path:
    """一家公司一個月的重大訊息。"""
    return repository.save_raw_response(
        "mops_t05st01", f"{stock_id}_{year:04d}{month:02d}",
        client.fetch_announcements(stock_id, year, month),
    )
