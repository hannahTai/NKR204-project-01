"""證交所資料擷取：只寫「每個端點的網址和參數」，其餘交給 common.py。

命名規則：
  fetch_xxx   → 只打 API，回傳 HTTP 回應，不判斷成敗、不留下任何檔案
  extract_xxx → fetch＋存成 raw 檔＋判斷成敗（回補、Airflow 呼叫這個）
"""
from pathlib import Path

import requests

from crawler.config import TWSE_BASE
from crawler.extract.common import http_get, save_response


def fetch_notice(date: str) -> requests.Response:
    """打證交所注意股 API，回傳 HTTP 回應（不檢查成敗）。

    date: 西元 YYYYMMDD，例如 "20261106"

    注意：沒開市的日子也回 stat="OK"，只是 data 為空、total 為 0。
    所以不能用 stat 判斷有沒有資料，也不能用 total==0 判斷是否為交易日。
    """
    return http_get(
        f"{TWSE_BASE}/announcement/notice",
        {
            "response": "json",
            "querytype": "1",
            "startDate": date,
            "endDate": date,      # 起訖同一天 = 只抓這一天
            "sortKind": "DATE",   # 依日期排序
        },
    )


def extract_notice(date: str) -> Path:
    """抓某一天的注意股並存成 raw 檔，回傳檔案路徑。

    成功：data/raw/twse_notice/<date>.json（同一天重跑會覆蓋，檔案數量不變）
    失敗：data/raw/twse_notice/<date>.error.json，然後丟出例外
    沒開市的日子也算成功、照樣存（data 是空的）：
    存了才分得出「查過、確實沒資料」和「根本沒查」。
    """
    return save_response("twse_notice", date, fetch_notice(date))
