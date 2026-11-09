"""transformer 的測試（注意股）：用真實回應裡的資料列當測試資料，不連網路、不讀 data/。

執行：uv run pytest
"""
import math
from datetime import date

import pandas as pd
import pytest

from crawler.date_utils import roc_to_date, roc_to_dates
from crawler.transformer import (
    NOTICE_FIELDS, cn_number, notice_to_frame, strip_html, to_number, transform_notice,
)


def envelope(rows, fields=NOTICE_FIELDS):
    """組一個最小的 raw 信封。"""
    return {"meta": {}, "body": {"stat": "OK", "fields": fields, "data": rows}}


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
    assert [cn_number(s) for s in ["一", "九", "十", "十三", "十四"]] == [1, 9, 10, 13, 14]
    assert strip_html(pd.Series(["<font color='#FF0000'>﹝第十款﹞</font>"])).tolist() == ["﹝第十款﹞"]


def test_to_number_rejects_garbage():
    """看不懂的數字要報錯，不能默默變成 NaN。"""
    with pytest.raises(ValueError):
        to_number(pd.Series(["12.3abc"]))


def test_basic_row():
    notices, clauses = run(ROW_ANDES)
    row = notices.iloc[0]
    assert (row["trade_date"], row["stock_id"], row["stock_name"], row["close"]) == (date(2026, 11, 6), "6533", "晶心科", 202.0)
    assert math.isnan(row["pe"])
    assert clauses.to_dict("records") == [{"trade_date": date(2026, 11, 6), "stock_id": "6533", "clause": 1}]


def test_html_stripped_and_multiple_clauses():
    notices, clauses = run(ROW_TENGHUI)
    assert "<font" not in notices.iloc[0]["info"]   # 用 ["info"]：.info 會撞到 pandas 內建的方法
    assert notices.iloc[0]["close"] == 1463.0            # 千分位逗號
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
