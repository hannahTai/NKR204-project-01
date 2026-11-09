"""公司公告資料擷取。

| 來源 | 存檔名稱（source/key） | 一次請求 = |
|---|---|---|
| 重大訊息 t05st01 | mops_t05st01/<代號>_<YYYYMM> | 一家公司的一個月 |

這個來源一次只能查一家公司、一個月 → 請求數 = 公司數 × 月份數，
這是之後要用佇列（Celery）、限速、重派的主要理由。
"""
from datetime import date
from pathlib import Path

import requests

from crawler.config import MOPS_BASE
from crawler.extract.common import http_post, save_response
from crawler.utils.dates import last_day_of_month


def announcements_body(stock_id: str, year: int, month: int) -> dict:
    """組出 t05st01 的 POST 內容。

    year / month: 西元年、月；API 要民國年，這裡自己換算
    當月只查到今天（還沒到的日子沒有資料），其他月份查到月底。
    """
    today = date.today()
    if (year, month) == (today.year, today.month):
        last_day = today.day
    else:
        last_day = last_day_of_month(year, month)
    return {
        "companyId": stock_id,
        "year": str(year - 1911),
        "month": str(month),
        "firstDay": "1",
        "lastDay": str(last_day),
    }


def fetch_announcements(stock_id: str, year: int, month: int) -> requests.Response:
    """打重大訊息 API（一家公司、一個月），回傳 HTTP 回應（不檢查成敗）。

    stock_id: 證券代號，例如 "2330"
    year / month: 西元年、月，例如 2026, 11
    """
    return http_post(f"{MOPS_BASE}/t05st01", announcements_body(stock_id, year, month))


def extract_announcements(stock_id: str, year: int, month: int) -> Path:
    """抓一家公司一個月的重大訊息並存成 raw 檔：data/raw/mops_t05st01/<代號>_<YYYYMM>.json

    POST 的參數不在網址裡，所以把送出的內容也存進 meta.request_body，才能重現請求。
    """
    body = announcements_body(stock_id, year, month)
    resp = http_post(f"{MOPS_BASE}/t05st01", body)
    return save_response("mops_t05st01", f"{stock_id}_{year:04d}{month:02d}", resp,
                         request_body=body)
