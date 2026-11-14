"""stage_data_transform 的測試：用真實回應的資料列，不連網路、不讀 data/。執行：uv run pytest"""
import datetime
import math
import warnings

import pandas as pd
import pytest

from common.date_utils import roc_to_date, roc_to_dates
from pipeline.transform.utils import chinese_number, strip_html, to_number
from pipeline.transform.rules import (
    announcement_to_frame, market_daily_to_frame, holiday_to_frame, punish_watchlist_to_frame,
    notice_to_frame, punish_to_frame, transform_announcement,
    transform_company, transform_holiday, transform_punish_watchlist, transform_notice,
    transform_punish, transform_trading_day,
)


# 官方回傳的完整欄位（照真實回應，含沒用到的欄位）
NOTICE_API_FIELDS = ["編號", "證券代號", "證券名稱", "累計次數", "注意交易資訊", "日期", "收盤價", "本益比"]
PUNISH_API_FIELDS = ["編號", "公布日期", "證券代號", "證券名稱", "累計", "處置條件",
                     "處置起迄時間", "處置措施", "處置內容", "備註"]
WATCHLIST_API_FIELDS = ["編號", "證券代號", "證券名稱", "近期達本公司「公布注意交易資訊」標準之情形"]
MARKET_API_FIELDS = ["日期", "成交股數", "成交金額", "成交筆數", "發行量加權股價指數", "漲跌點數"]
HOLIDAY_API_FIELDS = ["日期", "名稱", "說明"]


def envelope(rows, fields=NOTICE_API_FIELDS, fetched_at="2026-11-09T21:00:00+08:00", **body):
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


def run(*rows, fields=NOTICE_API_FIELDS):
    return transform_notice(notice_to_frame([envelope(list(rows), fields)]))


def test_clean_helpers():
    assert roc_to_date("115年11月06日") == datetime.date(2026, 11, 6)
    assert roc_to_dates(pd.Series(["115.11.06", "115/10/01"])).tolist() == [datetime.date(2026, 11, 6), datetime.date(2026, 10, 1)]
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
    assert (row["trade_date"], row["stock_id"], row["stock_name"], row["close_price"]) == (datetime.date(2026, 11, 6), "6533", "晶心科", 202.0)
    assert math.isnan(row["pe_ratio"])
    assert clauses.to_dict("records") == [{"trade_date": datetime.date(2026, 11, 6), "stock_id": "6533", "clause": 1}]


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


def test_missing_used_field_raises():
    """用得到的欄位不見了要報錯，不能默默變成空值。"""
    fields = [f for f in NOTICE_API_FIELDS if f != "收盤價"]
    row = [v for f, v in zip(NOTICE_API_FIELDS, ROW_ANDES) if f != "收盤價"]
    with pytest.raises(ValueError, match="收盤價"):
        notice_to_frame([envelope([row], fields=fields)])


def test_added_field_is_ignored():
    """官方多加一欄：照樣解析，新欄位不影響。"""
    notices, _ = run(ROW_ANDES + ["新欄位的值"], fields=NOTICE_API_FIELDS + ["新欄位"])
    assert notices.iloc[0]["stock_id"] == "6533"


def test_reordered_fields_still_work():
    """官方調整欄位順序：用欄名取，不受影響。"""
    notices, _ = run(ROW_ANDES[::-1], fields=NOTICE_API_FIELDS[::-1])
    assert (notices.iloc[0]["stock_id"], notices.iloc[0]["close_price"]) == ("6533", 202.0)


def test_unused_field_removed_is_fine():
    """沒用到的欄位（編號）拿掉：照樣解析。"""
    notices, _ = run(ROW_ANDES[1:], fields=NOTICE_API_FIELDS[1:])
    assert notices.iloc[0]["stock_id"] == "6533"


def test_company_missing_field_raises():
    """上市公司 API 沒有 fields：少了用得到的 key 也要報錯，不能載入空的公司代號。"""
    raw = {"meta": {"key": "20261109"}, "body": [{"公司名稱": "台灣水泥", "公司簡稱": "台泥", "產業別": "01",
                                                  "上市日期": "19620209"}]}
    with pytest.raises(ValueError, match="公司代號"):
        transform_company(raw)


def test_missing_clause_raises():
    row = ROW_ANDES.copy()
    row[4] = "沒有款次的文字"
    with pytest.raises(ValueError, match="款次"):
        run(row)


# ---------- 處置股 ----------
PUNISH_ROW = [1, "115/11/06", "2360", "致茂", 3, "連續三次", "115/11/09～115/11/13", "第一次處置",
              "１處置原因：…\n３處置措施：\nａ以人工管制之撮合終端機執行撮合作業（約每二分鐘撮合一次）。\n", "<a href='x'>連結</a>"]


def test_punish_parses_period_and_minutes():
    df = transform_punish(punish_to_frame([envelope([PUNISH_ROW], PUNISH_API_FIELDS)]))
    row = df.iloc[0]
    assert (row["announce_date"], row["period_start"], row["period_end"]) == (
        datetime.date(2026, 11, 6), datetime.date(2026, 11, 9), datetime.date(2026, 11, 13))
    assert row["match_interval_minutes"] == 2 and row["measure_type"] == "第一次處置" and not row["has_star_mark"]


def test_punish_dedup_keeps_latest_fetch():
    """同一筆公告出現在好幾天的 raw 裡 → 只留一筆，而且是最後抓到的版本。"""
    newer = PUNISH_ROW.copy()
    newer[3] = "致茂（新）"
    with warnings.catch_warnings():
        warnings.simplefilter("error")   # 不同份 raw 的新舊版本是正常情況，不該警告
        df = transform_punish(punish_to_frame([
            envelope([newer], PUNISH_API_FIELDS, fetched_at="2026-11-09T22:00:00+08:00"),
            envelope([PUNISH_ROW], PUNISH_API_FIELDS, fetched_at="2026-11-09T21:00:00+08:00"),
        ]))
    assert len(df) == 1 and df.iloc[0]["stock_name"] == "致茂（新）"


def test_punish_two_in_one_raw_warns():
    """同一份 raw 裡同一檔同一天有兩則不同的處置 → 警告（去重只會留一則）。"""
    other = PUNISH_ROW.copy()
    other[7] = "第二次處置"
    with pytest.warns(UserWarning, match="同一天同一檔有多則處置"):
        df = transform_punish(punish_to_frame([envelope([PUNISH_ROW, other], PUNISH_API_FIELDS)]))
    assert len(df) == 1


def test_punish_identical_rows_in_one_raw_no_warning():
    """同一份 raw 裡完全相同的兩列只是重複，不警告。"""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        df = transform_punish(punish_to_frame([envelope([PUNISH_ROW, PUNISH_ROW], PUNISH_API_FIELDS)]))
    assert len(df) == 1


def test_punish_star_kept_as_flag():
    row = PUNISH_ROW.copy()
    row[1] = "*115/11/09"
    df = transform_punish(punish_to_frame([envelope([row], PUNISH_API_FIELDS)]))
    assert df.iloc[0]["has_star_mark"] and df.iloc[0]["announce_date"] == datetime.date(2026, 11, 9)


# ---------- 注意累計名單 ----------
def test_punish_watchlist_date_from_title_and_br_split():
    raw = envelope([[1, "2455", "全新", "連續二次<br>九個營業日已有五次"]], WATCHLIST_API_FIELDS,
                   title="115年11月06日 公布注意累計次數可能達處置標準之有價證券一覽表")
    df = transform_punish_watchlist(punish_watchlist_to_frame([raw]))
    assert df.iloc[0]["data_date"] == datetime.date(2026, 11, 6)
    assert df.iloc[0]["progress_text"] == "連續二次\n九個營業日已有五次"


# ---------- 交易日、休市 ----------
def test_trading_day_numbers_and_dedup():
    rows = [["115/11/02", "10,422,514,115", "799,687,507,911", "4,104,242", "44,920.14", "-291.69"]]
    df = transform_trading_day(market_daily_to_frame([envelope(rows, MARKET_API_FIELDS)] * 2))   # 同月抓兩次
    assert len(df) == 1
    assert df.iloc[0]["volume_shares"] == 10422514115 and df.iloc[0]["taiex_change_points"] == -291.69


def test_holiday_is_western_date():
    df = transform_holiday(holiday_to_frame([envelope([["2026-10-09", "國慶日", "補假"]], HOLIDAY_API_FIELDS)]))
    assert df.iloc[0]["holiday_date"] == datetime.date(2026, 10, 9)


# ---------- 公司、重大訊息 ----------
def test_company_snapshot():
    raw = {"meta": {"key": "20261109"},
           "body": [{"公司代號": "1101", "公司簡稱": "台泥", "公司名稱": "臺灣水泥", "產業別": "01", "上市日期": "19620209"}]}
    row = transform_company(raw).iloc[0]
    assert (row["company_id"], row["listed_date"], row["snapshot_date"]) == ("1101", datetime.date(1962, 2, 9), datetime.date(2026, 11, 9))


ANNOUNCEMENT_TITLES = [{"main": m, "sub": []} for m in ["公司代號", "公司名稱", "發言日期", "發言時間", "主旨", "詳細資料"]]


def announcement_raw(data: list) -> dict:
    return {"meta": {}, "body": {"code": 200, "result": {"titles": ANNOUNCEMENT_TITLES, "data": data}}}


def test_announcement_serial_and_joined_subject():
    data = [["1303", "南亞", "115/09/01", "15:42:35", "因本公司有價證券達標準，\r\n故公布重大訊息",
             {"parameters": {"enterDate": "1150901", "serialNumber": "2"}}]]
    row = transform_announcement(announcement_to_frame([announcement_raw(data)])).iloc[0]
    assert (row["announce_date"], row["enter_date"], row["serial_number"]) == (
        datetime.date(2026, 9, 1), datetime.date(2026, 9, 1), 2)
    assert row["subject"] == "因本公司有價證券達標準，故公布重大訊息"


def test_announcement_same_day_same_serial_both_kept():
    """實際案例：1709 同一天發言的兩則公告序號都是 1（序號依輸入日期編），兩則都要留下。"""
    data = [["1709", "和益", "115/11/11", "15:32:02", "公告本公司董事會通過115年第三季合併財務報告",
             {"parameters": {"enterDate": "1151109", "serialNumber": "1"}}],
            ["1709", "和益", "115/11/11", "15:42:24", "公告本公司向關係人取得不動產使用權資產",
             {"parameters": {"enterDate": "1151111", "serialNumber": "1"}}]]
    out = transform_announcement(announcement_to_frame([announcement_raw(data)]))
    assert len(out) == 2
    assert out["enter_date"].tolist() == [datetime.date(2026, 11, 9), datetime.date(2026, 11, 11)]


def test_announcement_no_data_is_empty():
    """code 406「查無相符資料」：那個月沒有公告，result 是 null。"""
    raw = {"meta": {}, "body": {"code": 406, "message": "查無相符資料", "result": None}}
    assert transform_announcement(announcement_to_frame([raw])).empty
