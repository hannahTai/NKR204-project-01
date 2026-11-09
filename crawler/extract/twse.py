"""市場資料擷取：只寫「每個端點的網址和參數」，其餘交給 common.py。

命名規則：
  fetch_xxx   → 只打 API，回傳 HTTP 回應，不判斷成敗、不留下任何檔案
  extract_xxx → fetch＋存成 raw 檔＋判斷成敗（回補、Airflow 呼叫這個）

| 來源 | 存檔名稱（source/key） | 一次請求 = |
|---|---|---|
| 注意股 | twse_notice/YYYYMMDD | 一個交易日 |
| 處置股 | twse_punish/YYYYMMDD | 一個交易日（見 fetch_punish 的說明） |
| 注意累計名單 | twse_notetrans/YYYYMMDD | 只有最新一日，key 取回應裡的資料日期 |
| 開休市日期 | twse_holiday/YYYY | 一個年度 |
| 每日市場成交 | twse_fmtqik/YYYYMM | 一個月（交易日曆用） |
| 上市公司基本資料 | twse_t187ap03_L/YYYYMMDD | 全部公司的當日快照 |
"""
import re
from datetime import date
from pathlib import Path

import requests

from crawler.config import TWSE_BASE, TWSE_OPENAPI_BASE
from crawler.extract.common import http_get, parse_body, save_response
from crawler.utils.dates import DATE_FMT, roc_to_date, shift


# ---------- 注意股 ----------
def fetch_notice(date: str) -> requests.Response:
    """打注意股 API，回傳 HTTP 回應（不檢查成敗）。

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


# ---------- 處置股 ----------
PUNISH_LOOKAHEAD_DAYS = 14


def fetch_punish(date: str) -> requests.Response:
    """打處置股 API，回傳 HTTP 回應（不檢查成敗）。

    date: 西元 YYYYMMDD，例如 "20261106"

    注意：這個端點的 startDate / endDate 篩的是「處置期間」，不是公布日期。
    D 日公布的處置要從 D+1 才開始，只查 D 當天會漏掉 → 結束日往後多帶 14 天
    （跨春節連假也夠）。代價是同一筆公告會出現在好幾天的檔案裡，
    解析時要用（公布日期, 證券代號）去重。
    """
    return http_get(
        f"{TWSE_BASE}/announcement/punish",
        {
            "response": "json",
            "startDate": date,
            "endDate": shift(date, PUNISH_LOOKAHEAD_DAYS),
            "querytype": "3",
            "stockNo": "",
            "selectType": "",
            "proceType": "",
            "remarkType": "",
            "sortKind": "DATE",
        },
    )


def extract_punish(date: str) -> Path:
    """抓某一天的處置股並存成 raw 檔：data/raw/twse_punish/<date>.json"""
    return save_response("twse_punish", date, fetch_punish(date))


# ---------- 注意累計可能達處置標準名單（notetrans） ----------
def fetch_notetrans() -> requests.Response:
    """打 notetrans API，回傳 HTTP 回應（不檢查成敗）。

    這個端點沒有日期參數，只回最新一日；帶 date 參數也沒用（10/25 實測）。
    → 沒有歷史可以回補，只能從上線那天起每天存一份。
    """
    return http_get(f"{TWSE_BASE}/announcement/notetrans", {"response": "json"})


def notetrans_key(body: dict | list | str) -> str:
    """從回應的 title 取出資料日期當作 key；取不到就用今天。

    title 例如「…115年11月06日…」→ "20261106"
    用資料日期而不是抓取日期：週末抓到的是週五的名單，key 應該是週五。
    """
    title = body.get("title", "") if isinstance(body, dict) else ""
    m = re.search(r"\d+年\d+月\d+日", title)
    return roc_to_date(m.group()).strftime(DATE_FMT) if m else date.today().strftime(DATE_FMT)


def extract_notetrans() -> Path:
    """抓最新一日的 notetrans 並存成 raw 檔：data/raw/twse_notetrans/<資料日期>.json"""
    resp = fetch_notetrans()
    return save_response("twse_notetrans", notetrans_key(parse_body(resp)), resp)


# ---------- 開休市日期 ----------
def fetch_holiday(year: int) -> requests.Response:
    """打開休市日期 API（一整年），回傳 HTTP 回應（不檢查成敗）。

    year: 西元年，例如 2026；API 要民國年，這裡自己換算

    注意：這張表不含臨時休市（例如颱風假），交易日要以 fmtqik 為準。
    """
    return http_get(
        f"{TWSE_BASE}/holidaySchedule/holidaySchedule",
        {"response": "json", "queryYear": str(year - 1911)},
    )


def extract_holiday(year: int) -> Path:
    """抓某年的開休市日期並存成 raw 檔：data/raw/twse_holiday/<西元年>.json"""
    return save_response("twse_holiday", str(year), fetch_holiday(year))


# ---------- 每日市場成交資訊（交易日曆） ----------
def fetch_fmtqik(month: str) -> requests.Response:
    """打 FMTQIK（每日市場成交資訊，一整個月），回傳 HTTP 回應（不檢查成敗）。

    month: 西元 YYYYMM，例如 "202611"

    用途：回應裡每一列是一個「真的有交易」的日子 → 交易日曆。
    比開休市表可靠，臨時休市的日子不會出現在這裡。
    當月的資料會隨著每天收盤增加，所以當月要每天重抓。
    """
    return http_get(
        f"{TWSE_BASE}/afterTrading/FMTQIK",
        {"response": "json", "date": f"{month}01"},
    )


def extract_fmtqik(month: str) -> Path:
    """抓某個月的市場成交資訊並存成 raw 檔：data/raw/twse_fmtqik/<YYYYMM>.json"""
    return save_response("twse_fmtqik", month, fetch_fmtqik(month))


# ---------- 上市公司基本資料（OpenAPI） ----------
def fetch_companies() -> requests.Response:
    """打 OpenAPI t187ap03_L（全部上市公司基本資料），回傳 HTTP 回應（不檢查成敗）。

    OpenAPI 不能帶參數，只有當下這一份。
    用途：判斷某個代號是不是「公司股票」（排除權證、ETF、DR）、取得產業別。
    """
    return http_get(f"{TWSE_OPENAPI_BASE}/opendata/t187ap03_L", {})


def extract_companies() -> Path:
    """抓上市公司基本資料並存成 raw 檔：data/raw/twse_t187ap03_L/<今天>.json

    key 用抓取日期：這是某一天的快照，公司會上市、下市、改名。
    """
    today = date.today().strftime(DATE_FMT)
    return save_response("twse_t187ap03_L", today, fetch_companies())
