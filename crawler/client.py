"""抓資料：每個函式打一個 API，回傳 HTTP 回應（不判斷成敗、不存檔）。"""
import requests

from crawler import date_utils
from crawler.config import MOPS_BASE, TWSE_BASE, TWSE_OPENAPI_BASE

HEADERS = {   # 不像瀏覽器的請求會被擋
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": "application/json",
}
TIMEOUT = 30  # 秒


def http_get(url: str, params: dict) -> requests.Response:
    return requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)


def http_post(url: str, body: dict) -> requests.Response:
    return requests.post(url, json=body, headers=HEADERS, timeout=TIMEOUT)


def fetch_notice(day: str) -> requests.Response:
    """注意股，某一天（YYYYMMDD）。沒開市也回 stat="OK"，只是 data 為空。"""
    return http_get(f"{TWSE_BASE}/announcement/notice", {
        "response": "json", "querytype": "1", "startDate": day, "endDate": day, "sortKind": "DATE",
    })


def fetch_punish(day: str) -> requests.Response:
    """處置股，某一天（YYYYMMDD）。

    日期篩的是「處置期間」：當天公布的處置隔天才開始，所以結束日多帶 14 天。
    """
    return http_get(f"{TWSE_BASE}/announcement/punish", {
        "response": "json", "startDate": day, "endDate": date_utils.shift(day, 14),
        "querytype": "3", "stockNo": "", "selectType": "", "proceType": "", "remarkType": "",
        "sortKind": "DATE",
    })


def fetch_punish_watchlist() -> requests.Response:
    """注意累計可能達處置標準名單：只有最新一天，不接受日期參數。"""
    return http_get(f"{TWSE_BASE}/announcement/notetrans", {"response": "json"})


def fetch_holiday(year: int) -> requests.Response:
    """開休市日期，某一年（西元）。不含颱風等臨時休市。"""
    return http_get(f"{TWSE_BASE}/holidaySchedule/holidaySchedule",
                    {"response": "json", "queryYear": str(year - 1911)})


def fetch_market_daily(month: str) -> requests.Response:
    """每日市場成交資訊，某個月（YYYYMM）。每一列是一個有交易的日子。"""
    return http_get(f"{TWSE_BASE}/afterTrading/FMTQIK", {"response": "json", "date": f"{month}01"})


def fetch_companies() -> requests.Response:
    """上市公司基本資料：只有當下這一份。"""
    return http_get(f"{TWSE_OPENAPI_BASE}/opendata/t187ap03_L", {})


def fetch_announcements(stock_id: str, year: int, month: int) -> requests.Response:
    """公司重大訊息，一家公司一個月（西元年月）。本月只查到今天。"""
    today = date_utils.today()
    is_this_month = (year, month) == (today.year, today.month)
    last_day = today.day if is_this_month else date_utils.last_day_of_month(year, month)
    return http_post(f"{MOPS_BASE}/t05st01", {
        "companyId": stock_id, "year": str(year - 1911), "month": str(month),
        "firstDay": "1", "lastDay": str(last_day),
    })
