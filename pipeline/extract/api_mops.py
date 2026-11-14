"""公開資訊觀測站 API：公司重大訊息，一家公司一個月一個請求。

這裡只管「怎麼打 API」（網址、參數），回傳原始回應，不存檔。
存成 raw 檔的是 tasks.py。
"""
import calendar

import requests

from common import date_utils
from common.config import MOPS_BASE
from pipeline.extract.http_utils import http_post


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
