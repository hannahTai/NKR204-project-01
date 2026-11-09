"""資料來源層（client）：只負責「怎麼跟外部系統拿資料」。

這個檔案的邊界：
    知道每個端點的網址、參數名稱。
    不知道資料會被存到哪裡，也不知道誰會呼叫它。

上游改網址、改參數時，只有這個檔案要改。

回傳整個 HTTP 回應（不是整理好的資料），
因為 raw 層要連同網址、狀態碼一起原樣存下來（見 repository.save_raw_response）。

| 函式 | 一次請求 = |
|---|---|
| fetch_notice(date)        注意股          | 一個交易日 |
| fetch_punish(date)        處置股          | 一個交易日（見函式說明） |
| fetch_notetrans()         注意累計名單    | 只有最新一日，沒有參數 |
| fetch_holiday(year)       開休市日期      | 一個年度 |
| fetch_fmtqik(month)       每日市場成交    | 一個月（交易日曆用） |
| fetch_companies()         上市公司基本資料 | 當下的快照，沒有參數 |
| fetch_announcements(...)  公司重大訊息    | 一家公司的一個月 |
"""
from datetime import date

import requests

from crawler.config import MOPS_BASE, TWSE_BASE, TWSE_OPENAPI_BASE
from crawler.date_utils import last_day_of_month, shift

# 資料源會擋不像瀏覽器的請求，所以假裝成 Chrome
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
TIMEOUT = 30  # 秒；沒設的話，伺服器不回應時程式會一直卡住


def http_get(url: str, params: dict) -> requests.Response:
    """發 GET 請求，回傳 HTTP 回應（不檢查成敗）。

    params 交給 requests 組網址：它會自動處理 ? 和 &，以及特殊字元的編碼。
    """
    return requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)


def http_post(url: str, body: dict) -> requests.Response:
    """發 POST 請求（body 以 JSON 送出），回傳 HTTP 回應（不檢查成敗）。"""
    return requests.post(url, json=body, headers=HEADERS, timeout=TIMEOUT)


# ---------- 注意股 ----------
def fetch_notice(date: str) -> requests.Response:
    """注意股（某一個交易日、全部上市有價證券）。

    date: 西元 YYYYMMDD，例如 "20261106"

    注意：沒開市的日子也回 stat="OK"，只是 data 為空、total 為 0。
    所以不能用 stat 判斷有沒有資料，也不能用 total==0 判斷是否為交易日。
    """
    return http_get(f"{TWSE_BASE}/announcement/notice", {
        "response": "json",
        "querytype": "1",
        "startDate": date,
        "endDate": date,      # 起訖同一天 = 只抓這一天
        "sortKind": "DATE",   # 依日期排序
    })


# ---------- 處置股 ----------
PUNISH_LOOKAHEAD_DAYS = 14


def fetch_punish(date: str) -> requests.Response:
    """處置股。

    date: 西元 YYYYMMDD，例如 "20261106"

    注意：這個端點的 startDate / endDate 篩的是「處置期間」，不是公布日期。
    D 日公布的處置要從 D+1 才開始，只查 D 當天會漏掉 → 結束日往後多帶 14 天
    （跨春節連假也夠）。代價是同一筆公告會出現在好幾天的檔案裡，
    解析時要用（公布日期, 證券代號）去重。
    """
    return http_get(f"{TWSE_BASE}/announcement/punish", {
        "response": "json",
        "startDate": date,
        "endDate": shift(date, PUNISH_LOOKAHEAD_DAYS),
        "querytype": "3",
        "stockNo": "",
        "selectType": "",
        "proceType": "",
        "remarkType": "",
        "sortKind": "DATE",
    })


# ---------- 注意累計可能達處置標準名單（notetrans） ----------
def fetch_notetrans() -> requests.Response:
    """注意累計名單：沒有日期參數，只回最新一日。

    帶任何日期參數都沒用（10/25、11/09 實測 6 種寫法，回應的 params 為空，伺服器不讀參數）
    → 沒有歷史可以回補，只能從上線那天起每天存一份。
    """
    return http_get(f"{TWSE_BASE}/announcement/notetrans", {"response": "json"})


# ---------- 開休市日期 ----------
def fetch_holiday(year: int) -> requests.Response:
    """開休市日期（一整年）。

    year: 西元年，例如 2026；API 要民國年，這裡自己換算
    注意：這張表不含臨時休市（例如 10/23 颱風假），交易日以 fmtqik 為準。
    """
    return http_get(f"{TWSE_BASE}/holidaySchedule/holidaySchedule",
                    {"response": "json", "queryYear": str(year - 1911)})


# ---------- 每日市場成交資訊（交易日曆） ----------
def fetch_fmtqik(month: str) -> requests.Response:
    """每日市場成交資訊（一整個月）。

    month: 西元 YYYYMM，例如 "202611"
    用途：每一列是一個「真的有交易」的日子 → 交易日曆；臨時休市的日子不會出現。
    當月的資料會隨著每天收盤增加，所以當月要每天重抓。
    """
    return http_get(f"{TWSE_BASE}/afterTrading/FMTQIK",
                    {"response": "json", "date": f"{month}01"})


# ---------- 上市公司基本資料（OpenAPI） ----------
def fetch_companies() -> requests.Response:
    """全部上市公司基本資料（OpenAPI t187ap03_L）：不能帶參數，只有當下這一份。

    用途：判斷某個代號是不是「公司股票」（排除權證、ETF、DR）、取得產業別。
    """
    return http_get(f"{TWSE_OPENAPI_BASE}/opendata/t187ap03_L", {})


# ---------- 公司重大訊息 ----------
def announcements_body(stock_id: str, year: int, month: int) -> dict:
    """組出重大訊息 API 的 POST 內容。

    year / month: 西元年、月；API 要民國年，這裡自己換算
    當月只查到今天（還沒到的日子沒有資料），其他月份查到月底。
    """
    today = date.today()
    last_day = today.day if (year, month) == (today.year, today.month) else last_day_of_month(year, month)
    return {
        "companyId": stock_id,
        "year": str(year - 1911),
        "month": str(month),
        "firstDay": "1",
        "lastDay": str(last_day),
    }


def fetch_announcements(stock_id: str, year: int, month: int) -> requests.Response:
    """一家公司一個月的重大訊息（POST）。

    這個來源一次只能查一家公司、一個月 → 請求數 = 公司數 × 月份數，
    這是之後要用佇列（Celery）、限速、重派的主要理由。
    送出的內容可以從 resp.request.body 取回，存 raw 時會一起記下來。
    """
    return http_post(f"{MOPS_BASE}/t05st01", announcements_body(stock_id, year, month))
