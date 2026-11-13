"""抓市場資料：注意股、處置股、注意累計名單、開休市日期、每日市場成交、上市公司清單。

fetch_xxx 打 API 回傳回應；crawler_xxx 抓一份存成 raw，回傳檔案路徑。
"""
import pathlib
import re

import pandas as pd
import requests

from crawler import raw_file
from crawler.config import TWSE_BASE, TWSE_OPENAPI_BASE
from crawler.date_utils import DATE_FMT, roc_to_date, today_yyyymmdd
from crawler.http_utils import http_get


# ---------- 注意股 ----------
def fetch_notice(yyyymmdd: str) -> requests.Response:
    """某一天（YYYYMMDD）。沒開市也回 stat="OK"，只是 data 為空。"""
    return http_get(f"{TWSE_BASE}/announcement/notice", {
        "response": "json", "querytype": "1", "startDate": yyyymmdd, "endDate": yyyymmdd, "sortKind": "DATE",
    })


def crawler_notice(yyyymmdd: str) -> pathlib.Path:
    return raw_file.save_raw_response("notice", yyyymmdd, fetch_notice(yyyymmdd))


# ---------- 處置股 ----------
def fetch_punish(yyyymmdd: str) -> requests.Response:
    """某一天（YYYYMMDD）處置中＋當天公布的處置。

    篩的是處置期間；當天公布的下一個交易日才開始，連假可能隔 10 天左右，所以結束日多帶 14 天。
    """
    return http_get(f"{TWSE_BASE}/announcement/punish", {
        "response": "json", "startDate": yyyymmdd, "endDate": (pd.Timestamp(yyyymmdd) + pd.Timedelta(days=14)).strftime("%Y%m%d"),
        "querytype": "3", "stockNo": "", "selectType": "", "proceType": "", "remarkType": "",
        "sortKind": "DATE",
    })


def crawler_punish(yyyymmdd: str) -> pathlib.Path:
    return raw_file.save_raw_response("punish", yyyymmdd, fetch_punish(yyyymmdd))


# ---------- 注意累計可能達處置標準名單 ----------
def fetch_punish_watchlist() -> requests.Response:
    """只有最新一天，不接受日期參數。"""
    return http_get(f"{TWSE_BASE}/announcement/notetrans", {"response": "json"})


def watchlist_date(body) -> str | None:
    """從標題取出名單的資料日期（YYYYMMDD），找不到就回傳 None。

    標題例如「115年11月12日 公布注意累計次數可能達處置標準之有價證券一覽表」
    """
    if not isinstance(body, dict):   # 被擋時回傳的是 HTML 文字，不是 dict
        return None

    found = re.search(r"\d+年\d+月\d+日", body.get("title", ""))
    if found is None:
        return None

    roc_text = found.group()             # "115年11月12日"
    data_date = roc_to_date(roc_text)    # datetime.date(2026, 11, 12)
    return data_date.strftime(DATE_FMT)  # "20261112"


def crawler_punish_watchlist() -> pathlib.Path:
    """檔名用名單上的資料日期（週末抓到的是週五的名單）。"""
    resp = fetch_punish_watchlist()
    key = watchlist_date(raw_file.parse_body(resp))
    if key is None:   # 找不到日期：用今天，至少把回應存下來查原因
        key = today_yyyymmdd()
    return raw_file.save_raw_response("punish_watchlist", key, resp)


# ---------- 開休市日期 ----------
def fetch_holiday(year: int) -> requests.Response:
    """某一年（西元）。不含颱風等臨時休市。"""
    return http_get(f"{TWSE_BASE}/holidaySchedule/holidaySchedule",
                    {"response": "json", "queryYear": str(year - 1911)})


def crawler_holiday(year: int) -> pathlib.Path:
    return raw_file.save_raw_response("holiday", str(year), fetch_holiday(year))


# ---------- 每日市場成交 ----------
def fetch_market_daily(yyyymm: str) -> requests.Response:
    """某個月（YYYYMM）。每一列是一個有交易的日子。"""
    return http_get(f"{TWSE_BASE}/afterTrading/FMTQIK", {"response": "json", "date": f"{yyyymm}01"})


def crawler_market_daily(yyyymm: str) -> pathlib.Path:
    return raw_file.save_raw_response("market_daily", yyyymm, fetch_market_daily(yyyymm))


# ---------- 上市公司清單 ----------
def fetch_companies() -> requests.Response:
    """只有當下這一份。"""
    return http_get(f"{TWSE_OPENAPI_BASE}/opendata/t187ap03_L", {})


def crawler_companies() -> pathlib.Path:
    """檔名用抓取日期（每天一份快照）。"""
    return raw_file.save_raw_response("companies", today_yyyymmdd(), fetch_companies())
