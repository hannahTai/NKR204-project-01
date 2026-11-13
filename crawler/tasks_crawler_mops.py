"""抓公司重大訊息：一家公司一個月一個請求。

fetch_announcements 打 API 回傳回應；crawler_announcements 存成 raw，回傳檔案路徑。
"""
import calendar
import pathlib

import requests

from crawler import date_utils, raw_file
from crawler.config import MOPS_BASE
from crawler.http_utils import http_post


def fetch_announcements(stock_id: str, year: int, month: int) -> requests.Response:
    """西元年月。本月只查到今天。"""
    today = date_utils.today()
    if (year, month) == (today.year, today.month):
        last_day = today.day                              # 本月：查到今天
    else:
        last_day = calendar.monthrange(year, month)[1]    # 其他月：查到月底（monthrange 回傳 (星期幾, 天數)）

    return http_post(f"{MOPS_BASE}/t05st01", {
        "companyId": stock_id, "year": str(year - 1911), "month": str(month),
        "firstDay": "1", "lastDay": str(last_day),
    })


def crawler_announcements(stock_id: str, year: int, month: int) -> pathlib.Path:
    key = f"{stock_id}_{year:04d}{month:02d}"   # 例如 1303_202611
    return raw_file.save_raw_response("announcements", key, fetch_announcements(stock_id, year, month))
