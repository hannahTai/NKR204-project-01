"""抓資料的任務：每個任務抓一份資料、存成 raw 檔，回傳檔案路徑。

打 API 的細節在 api_twse.py、api_mops.py；這裡只決定「存成哪個來源、哪個檔名（key）」。
producer.py 決定要跑哪些任務；之後接 Celery 時，重試、限速也加在這裡。
"""
import pathlib

from common.date_utils import today_yyyymmdd
from pipeline.extract import api_mops, api_twse, raw_file


# ---------- 證交所 ----------
def download_notice(yyyymmdd: str) -> pathlib.Path:
    """注意股：一天一份，檔名 20261113.json。"""
    return raw_file.save_raw_response("notice", yyyymmdd, api_twse.fetch_notice(yyyymmdd))


def download_punish(yyyymmdd: str) -> pathlib.Path:
    """處置股：一天一份，檔名 20261113.json。"""
    return raw_file.save_raw_response("punish", yyyymmdd, api_twse.fetch_punish(yyyymmdd))


def download_punish_watchlist() -> pathlib.Path:
    """注意累計名單：檔名用名單上的資料日期（週末抓到的是週五的名單）。"""
    resp = api_twse.fetch_punish_watchlist()
    key = api_twse.watchlist_date(raw_file.parse_body(resp))
    if key is None:   # 找不到日期：用今天，至少把回應存下來查原因
        key = today_yyyymmdd()
    return raw_file.save_raw_response("punish_watchlist", key, resp)


def download_holiday(year: int) -> pathlib.Path:
    """開休市日期：一年一份，檔名 2026.json。"""
    return raw_file.save_raw_response("holiday", str(year), api_twse.fetch_holiday(year))


def download_market_daily(yyyymm: str) -> pathlib.Path:
    """每日市場成交：一個月一份，檔名 202611.json。"""
    return raw_file.save_raw_response("market_daily", yyyymm, api_twse.fetch_market_daily(yyyymm))


def download_companies() -> pathlib.Path:
    """上市公司清單：檔名用抓取日期（每天一份快照）。"""
    return raw_file.save_raw_response("companies", today_yyyymmdd(), api_twse.fetch_companies())


# ---------- 觀測站 ----------
def download_announcements(stock_id: str, year: int, month: int) -> pathlib.Path:
    """重大訊息：一家公司一個月一份，檔名 1303_202611.json。"""
    key = f"{stock_id}_{year:04d}{month:02d}"
    return raw_file.save_raw_response("announcements", key, api_mops.fetch_announcements(stock_id, year, month))
