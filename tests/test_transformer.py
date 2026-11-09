"""transformer 的測試：用真實回應的資料列，不連網路、不讀 data/。執行：uv run pytest"""
import math
from datetime import date

import pandas as pd
import pytest

from crawler.date_utils import roc_to_date, roc_to_dates
from crawler.transformer import (
    MARKET_DAILY_FIELDS, HOLIDAY_FIELDS, PUNISH_WATCHLIST_FIELDS, NOTICE_FIELDS, PUNISH_FIELDS,
    announcement_to_frame, chinese_number, market_daily_to_frame, holiday_to_frame, punish_watchlist_to_frame,
    notice_to_frame, punish_to_frame, strip_html, to_number, transform_announcement,
    transform_company, transform_holiday, transform_punish_watchlist, transform_notice,
    transform_punish, transform_trading_day,
)


def envelope(rows, fields=NOTICE_FIELDS, fetched_at="2026-11-09T21:00:00+08:00", **body):
    """組一個最小的 raw 信封。"""
    return {"meta": {"fetched_at": fetched_at}, "body": {"stat": "OK", "fields": fields, "data": rows, **body}}


# 11/06 真實資料（晶心科：一般款次；騰輝：第十款被紅字包起來）
ROW_ANDES = [1, "6533", "晶心科", "38",
             "最近六個營業日累積收盤價跌幅達33.02%。且六個營業日起迄兩個營業日收盤價價差達75.50 元﹝第一款﹞。",
             "115.11.06", "202.00", "-----"]
ROW_TENGHUI = [1, "6672", "騰輝電子-KY", "38",
               "11月06日之本益比為69.94﹝第六款﹞。最近六個營業日之累積週轉率為73.98%。"
               "<font color='#FF0000'>﹝第十款﹞</font>。",
               "115.11.06", "1,463.00", "69.94"]


def run(*rows, fields=NOTICE_FIELDS):
    return transform_notice(notice_to_frame([envelope(list(rows), fields)]))


def test_clean_helpers():
    assert roc_to_date("115年11月06日") == date(2026, 11, 6)
    assert roc_to_dates(pd.Series(["115.11.06", "115/10/01"])).tolist() == [date(2026, 11, 6), date(2026, 10, 1)]
    nums = to_number(pd.Series(["1,450.00", "-----", ""])).tolist()
    assert nums[0] == 1450.0 and math.isnan(nums[1]) and math.isnan(nums[2])
    assert [chinese_number(s) for s in ["一", "九", "十", "十三", "十四"]] == [1, 9, 10, 13, 14]
    assert strip_html(pd.Series(["<font color='#FF0000'>﹝第十款﹞</font>"])).tolist() == ["﹝第十款﹞"]


def test_to_number_rejects_garbage():
    """看不懂的數字要報錯，不能默默變成 NaN。"""
    with pytest.raises(ValueError):
        to_number(pd.Series(["12.3abc"]))


def test_basic_row():
    notices, clauses = run(ROW_ANDES)
    row = notices.iloc[0]
    assert (row["trade_date"], row["stock_id"], row["stock_name"], row["close_price"]) == (date(2026, 11, 6), "6533", "晶心科", 202.0)
    assert math.isnan(row["pe_ratio"])
    assert clauses.to_dict("records") == [{"trade_date": date(2026, 11, 6), "stock_id": "6533", "clause": 1}]


def test_html_stripped_and_multiple_clauses():
    notices, clauses = run(ROW_TENGHUI)
    assert "<font" not in notices.iloc[0]["reason_text"]   # 用 ["欄位"] 取值，避免撞到 pandas 方法名
    assert notices.iloc[0]["close_price"] == 1463.0            # 千分位逗號
    assert clauses["clause"].tolist() == [6, 10]


def test_duplicate_clause_in_one_row_counted_once():
    row = ROW_ANDES.copy()
    row[4] = "﹝第三款﹞﹝第一款﹞﹝第三款﹞"
    _, clauses = run(row)
    assert clauses["clause"].tolist() == [1, 3]


def test_many_rows_keep_their_own_clauses():
    notices, clauses = run(ROW_ANDES, ROW_TENGHUI)
    assert len(notices) == 2
    assert clauses.groupby("stock_id")["clause"].apply(list).to_dict() == {"6533": [1], "6672": [6, 10]}


def test_empty_day_returns_empty_frames():
    """沒開市：stat 還是 OK，但 data 是空的。"""
    notices, clauses = run()
    assert notices.empty and clauses.empty


def test_changed_fields_raise():
    """上游改了欄位要報錯，不能默默解析出錯的資料。"""
    with pytest.raises(ValueError, match="欄位"):
        notice_to_frame([envelope([ROW_ANDES[:2]], fields=["編號", "證券代號"])])


def test_missing_clause_raises():
    row = ROW_ANDES.copy()
    row[4] = "沒有款次的文字"
    with pytest.raises(ValueError, match="款次"):
        run(row)


# ---------- 處置股 ----------
PUNISH_ROW = [1, "115/11/06", "2360", "致茂", 3, "連續三次", "115/11/09～115/11/13", "第一次處置",
              "１處置原因：…\n３處置措施：\nａ以人工管制之撮合終端機執行撮合作業（約每二分鐘撮合一次）。\n", "<a href='x'>連結</a>"]


def test_punish_parses_period_and_minutes():
    df = transform_punish(punish_to_frame([envelope([PUNISH_ROW], PUNISH_FIELDS)]))
    row = df.iloc[0]
    assert (row["announce_date"], row["period_start"], row["period_end"]) == (
        date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 13))
    assert row["match_interval_minutes"] == 2 and row["measure_type"] == "第一次處置" and not row["has_star_mark"]


def test_punish_dedup_keeps_latest_fetch():
    """同一筆公告出現在好幾天的 raw 裡 → 只留一筆，而且是最後抓到的版本。"""
    newer = PUNISH_ROW.copy()
    newer[3] = "致茂（新）"
    df = transform_punish(punish_to_frame([
        envelope([newer], PUNISH_FIELDS, fetched_at="2026-11-09T22:00:00+08:00"),
        envelope([PUNISH_ROW], PUNISH_FIELDS, fetched_at="2026-11-09T21:00:00+08:00"),
    ]))
    assert len(df) == 1 and df.iloc[0]["stock_name"] == "致茂（新）"


def test_punish_star_kept_as_flag():
    row = PUNISH_ROW.copy()
    row[1] = "*115/11/09"
    df = transform_punish(punish_to_frame([envelope([row], PUNISH_FIELDS)]))
    assert df.iloc[0]["has_star_mark"] and df.iloc[0]["announce_date"] == date(2026, 11, 9)


# ---------- 注意累計名單 ----------
def test_punish_watchlist_date_from_title_and_br_split():
    raw = envelope([[1, "2455", "全新", "連續二次<br>九個營業日已有五次"]], PUNISH_WATCHLIST_FIELDS,
                   title="115年11月06日 公布注意累計次數可能達處置標準之有價證券一覽表")
    df = transform_punish_watchlist(punish_watchlist_to_frame([raw]))
    assert df.iloc[0]["data_date"] == date(2026, 11, 6)
    assert df.iloc[0]["progress_text"] == "連續二次\n九個營業日已有五次"


# ---------- 交易日、休市 ----------
def test_trading_day_numbers_and_dedup():
    rows = [["115/11/02", "10,422,514,115", "799,687,507,911", "4,104,242", "44,920.14", "-291.69"]]
    df = transform_trading_day(market_daily_to_frame([envelope(rows, MARKET_DAILY_FIELDS)] * 2))   # 同月抓兩次
    assert len(df) == 1
    assert df.iloc[0]["volume_shares"] == 10422514115 and df.iloc[0]["taiex_change_points"] == -291.69


def test_holiday_is_western_date():
    df = transform_holiday(holiday_to_frame([envelope([["2026-10-09", "國慶日", "補假"]], HOLIDAY_FIELDS)]))
    assert df.iloc[0]["holiday_date"] == date(2026, 10, 9)


# ---------- 公司、重大訊息 ----------
def test_company_snapshot():
    raw = {"meta": {"key": "20261109"},
           "body": [{"公司代號": "1101", "公司簡稱": "台泥", "公司名稱": "臺灣水泥", "產業別": "01", "上市日期": "19620209"}]}
    row = transform_company(raw).iloc[0]
    assert (row["company_id"], row["listed_date"], row["snapshot_date"]) == ("1101", date(1962, 2, 9), date(2026, 11, 9))


def test_announcement_serial_and_joined_subject():
    titles = [{"main": m, "sub": []} for m in ["公司代號", "公司名稱", "發言日期", "發言時間", "主旨", "詳細資料"]]
    data = [["1303", "南亞", "115/09/01", "15:42:35", "因本公司有價證券達標準，\r\n故公布重大訊息",
             {"parameters": {"serialNumber": "2"}}]]
    raw = {"meta": {}, "body": {"code": 200, "result": {"titles": titles, "data": data}}}
    row = transform_announcement(announcement_to_frame([raw])).iloc[0]
    assert (row["announce_date"], row["serial_number"]) == (date(2026, 9, 1), 2)
    assert row["subject"] == "因本公司有價證券達標準，故公布重大訊息"


def test_announcement_no_data_is_empty():
    """code 406「查無相符資料」：那個月沒有公告，result 是 null。"""
    raw = {"meta": {}, "body": {"code": 406, "message": "查無相符資料", "result": None}}
    assert transform_announcement(announcement_to_frame([raw])).empty
